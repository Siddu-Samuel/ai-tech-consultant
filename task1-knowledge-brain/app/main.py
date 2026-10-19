"""FastAPI entry point for the Knowledge Brain."""

import asyncio
import hashlib
import logging
import re
import secrets
import time
from functools import lru_cache
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException

from app.config import get_settings
from app.crawler import KnowledgeCrawler, Manifest, manifest_status
from app.answering import ClaudeAnswerer, ExtractiveTestAnswerer, validate_citations
from app.database import KnowledgeStore
from app.embeddings import create_embedder
from app.image_analysis import analyze_manifest_images
from app.indexing import index_manifest
from app.retrieval import has_conflicting_evidence, retrieve
from app.schemas import (
    EscalationCreateRequest,
    EscalationResolveRequest,
    HealthResponse,
    ImageReference,
    IngestionRequest,
    IngestionStatusResponse,
    QueryRequest,
    QueryResponse,
)

settings = get_settings()
logger = logging.getLogger(__name__)
app = FastAPI(title="AI Tech Consultant — Knowledge Brain", version="0.1.0")
ingestion_lock = asyncio.Lock()


@lru_cache
def get_store() -> KnowledgeStore:
    store = KnowledgeStore(settings.database_url, settings.embedding_dimensions, settings.embedding_provider)
    store.initialize()
    return store


@lru_cache
def get_embedder():
    return create_embedder(settings)


@lru_cache
def get_answer_generator():
    if settings.demo_mode:
        return ExtractiveTestAnswerer()
    return ClaudeAnswerer(settings.anthropic_api_key, settings.claude_model_primary)


def _require_admin(token: str | None) -> None:
    configured = settings.admin_api_token
    if settings.app_env.lower() == "production" and not configured:
        raise HTTPException(status_code=503, detail="Admin API token is not configured")
    if configured and (token is None or not secrets.compare_digest(token, configured)):
        raise HTTPException(status_code=401, detail="Valid X-Admin-Token header required")


def _insufficient(request_id: str, answer: str, escalation_id: str, *, model: str | None = None) -> QueryResponse:
    return QueryResponse(
        answer=answer,
        status="insufficient_evidence",
        sources=[],
        image_references=[],
        needs_human=True,
        escalation_id=escalation_id,
        request_id=request_id,
        mode="demo" if settings.demo_mode else "live",
        model=model,
    )


def _audit_query(
    store: KnowledgeStore | None,
    request_id: str,
    question: str,
    status: str,
    evidence: list[dict[str, object]],
    model_id: str | None,
    started_at: float,
    answer: str = "",
    usage: dict[str, int] | None = None,
) -> None:
    if store is None:
        return
    try:
        store.record_query_audit(
            request_id,
            hashlib.sha256(question.encode("utf-8")).hexdigest(),
            status,
            evidence,
            model_id,
            "knowledge-answer-v1",
            int((time.perf_counter() - started_at) * 1000),
            usage.get("input_tokens") if usage else None,
            usage.get("output_tokens") if usage else None,
            answer,
        )
    except Exception:
        logger.exception("Query audit write failed; request_id=%s", request_id)


@app.get("/health", response_model=HealthResponse, tags=["operations"])
async def health() -> HealthResponse:
    return HealthResponse(
        service=settings.service_name,
        mode="demo" if settings.demo_mode else "live",
    )


@app.post("/ingestion/run", response_model=IngestionStatusResponse, tags=["ingestion"])
async def run_ingestion(request: IngestionRequest) -> IngestionStatusResponse:
    if ingestion_lock.locked():
        raise HTTPException(status_code=409, detail="An ingestion run is already active")
    async with ingestion_lock:
        try:
            store = get_store()
            lease = store.acquire_ingestion_lease()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Knowledge storage is unavailable ({type(exc).__name__})") from exc
        if not lease.acquired:
            raise HTTPException(status_code=409, detail="An ingestion run is already active on another worker")
        crawler = KnowledgeCrawler(
            Manifest(settings.crawl_manifest_path),
            user_agent=settings.crawl_user_agent,
            delay_seconds=settings.crawl_delay_seconds,
            max_retries=settings.crawl_max_retries,
        )
        try:
            run = await crawler.run(request.max_pages)
            manifest = crawler.manifest
            if run["status"] in {"completed", "completed_with_errors"}:
                image_counts = await analyze_manifest_images(manifest.data, settings)
                manifest.save()
                embedder = get_embedder()
                model_label = settings.embedding_model or settings.embedding_provider
                index_counts = await index_manifest(
                    manifest.data,
                    store,
                    embedder,
                    model_label=model_label,
                    dimensions=settings.embedding_dimensions,
                )
                store.sync_ingestion(manifest.data)
                if image_counts["failed"]:
                    run["errors"].append(f"{image_counts['failed']} image(s) failed analysis")
                run["indexed_chunks"] = index_counts["chunks"]
            manifest.data["runs"][-1].update(run)
            manifest.save()
            store.sync_ingestion(manifest.data)
            return IngestionStatusResponse(**run)
        except Exception as exc:
            logger.exception("Knowledge ingestion/index synchronization failed")
            manifest = crawler.manifest
            if manifest.data.get("runs"):
                manifest.data["runs"][-1]["status"] = "completed_with_errors"
                manifest.data["runs"][-1].setdefault("errors", []).append(f"index synchronization failed: {type(exc).__name__}")
                manifest.save()
            raise HTTPException(status_code=503, detail=f"Ingestion could not be indexed ({type(exc).__name__})") from exc
        finally:
            lease.release()


@app.get("/ingestion/status", tags=["ingestion"])
async def ingestion_status() -> dict[str, object]:
    return manifest_status(Manifest(settings.crawl_manifest_path))


@app.post("/query", response_model=QueryResponse, tags=["knowledge"])
async def query_knowledge(request: QueryRequest, x_service_token: str | None = Header(default=None), x_request_id: str | None = Header(default=None)) -> QueryResponse:
    request_id = x_request_id if x_request_id and re.fullmatch(r"[A-Za-z0-9._:-]{8,120}", x_request_id) else str(uuid4())
    started_at = time.perf_counter()
    question = request.question.strip()
    if request.customer_id:
        configured_token = settings.task1_service_token
        if not configured_token:
            raise HTTPException(status_code=503, detail="Customer-scoped knowledge access is not configured")
        if x_service_token is None or not secrets.compare_digest(x_service_token, configured_token):
            raise HTTPException(status_code=401, detail="Valid X-Service-Token header required for customer-scoped knowledge")
    if request.context:
        question = f"{question}\nContext: {request.context.strip()}"
    store: KnowledgeStore | None = None
    try:
        store = get_store()
        results = await retrieve(question, store, get_embedder(), limit=settings.retrieval_limit, customer_id=request.customer_id)
    except Exception as exc:
        logger.exception("Knowledge retrieval failed; request_id=%s", request_id)
        if store is None:
            raise HTTPException(status_code=503, detail="Knowledge storage is unavailable; no answer was generated") from exc
        escalation_id = store.create_escalation(question, f"retrieval failed ({type(exc).__name__})", [], request_id)
        _audit_query(store, request_id, question, "retrieval_failed", [], None, started_at)
        return _insufficient(request_id, "The knowledge service could not retrieve evidence. A human review has been requested.", escalation_id)

    evidence = [item for item in results if item["score"] >= settings.retrieval_min_score]
    if not evidence:
        escalation_id = store.create_escalation(question, "No sufficiently relevant active documentation was retrieved", [], request_id)
        _audit_query(store, request_id, question, "insufficient_evidence", [], None, started_at)
        return _insufficient(request_id, "I could not find reliable documentation for this question. A human review has been requested.", escalation_id)

    if has_conflicting_evidence(question, evidence):
        escalation_id = store.create_escalation(question, "Retrieved sources contain conflicting capability statements", evidence, request_id)
        _audit_query(store, request_id, question, "conflicting_evidence", evidence, None, started_at)
        return _insufficient(request_id, "The retrieved documentation is conflicting. A human review has been requested.", escalation_id)

    for item in evidence:
        image_urls = item.get("metadata", {}).get("image_urls", [])
        item["images"] = store.get_image_references(item["article_id"], image_urls)

    model_name: str | None = None
    try:
        generator = get_answer_generator()
        model_name = "deterministic-extractive-demo" if settings.demo_mode else settings.claude_model_primary
    except Exception as exc:
        escalation_id = store.create_escalation(question, f"live model unavailable ({type(exc).__name__})", evidence, request_id)
        _audit_query(store, request_id, question, "model_unavailable", evidence, None, started_at)
        return _insufficient(request_id, "A human review is required because the answer model is not configured.", escalation_id)

    try:
        answer, citation_ids = await generator.generate(question, evidence)
    except Exception as exc:
        logger.exception("Answer generation failed; request_id=%s", request_id)
        escalation_id = store.create_escalation(question, f"answer generation failed ({type(exc).__name__})", evidence, request_id)
        _audit_query(store, request_id, question, "generation_failed", evidence, model_name, started_at, usage=getattr(generator, "last_usage", None))
        return _insufficient(request_id, "I could not generate a verified answer. A human review has been requested.", escalation_id, model=model_name)

    citations = validate_citations(citation_ids, evidence)
    if not answer or not citations:
        escalation_id = store.create_escalation(question, "Answer did not include a valid source citation", evidence, request_id)
        _audit_query(store, request_id, question, "invalid_citation", evidence, model_name, started_at, answer, getattr(generator, "last_usage", None))
        return _insufficient(request_id, "The retrieved material did not support a citable answer. A human review has been requested.", escalation_id, model=model_name)

    images: list[ImageReference] = []
    seen_images: set[str] = set()
    for cited in citations:
        source = next(item for item in evidence if item["chunk_id"] == cited["chunk_id"])
        metadata = source.get("metadata", {})
        urls = metadata.get("image_urls", [])
        for image in store.get_image_references(source["article_id"], urls):
            if image["url"] not in seen_images:
                images.append(ImageReference(**image))
                seen_images.add(image["url"])
    _audit_query(store, request_id, question, "answered", evidence, model_name, started_at, answer, getattr(generator, "last_usage", None))
    return QueryResponse(
        answer=answer,
        status="answered",
        sources=citations,
        image_references=images,
        needs_human=False,
        escalation_id=None,
        request_id=request_id,
        mode="demo" if settings.demo_mode else "live",
        model=model_name,
    )


@app.get("/escalations", tags=["escalations"])
async def list_escalations(include_resolved: bool = False, x_admin_token: str | None = Header(default=None)) -> list[dict[str, object]]:
    _require_admin(x_admin_token)
    return get_store().list_escalations(include_resolved)


@app.post("/escalations", tags=["escalations"])
async def create_escalation(request: EscalationCreateRequest, x_admin_token: str | None = Header(default=None)) -> dict[str, str]:
    _require_admin(x_admin_token)
    escalation_id = get_store().create_escalation(request.question, request.reason, request.evidence, request.request_id)
    return {"id": escalation_id, "status": "open"}


@app.post("/escalations/{escalation_id}/resolve", tags=["escalations"])
async def resolve_escalation(escalation_id: str, request: EscalationResolveRequest, x_admin_token: str | None = Header(default=None)) -> dict[str, str]:
    _require_admin(x_admin_token)
    if request.scope == "customer" and not request.customer_id:
        raise HTTPException(status_code=422, detail="customer_id is required for customer-scoped knowledge")
    try:
        vector = await get_embedder().embed(request.answer)
        updated = get_store().resolve_escalation(
            escalation_id, request.answer, request.reviewer, request.scope, request.customer_id, vector, request.expires_at
        )
    except Exception as exc:
        logger.exception("Escalation resolution failed")
        raise HTTPException(status_code=503, detail=f"Escalation could not be resolved ({type(exc).__name__})") from exc
    if not updated:
        raise HTTPException(status_code=409, detail="Escalation does not exist or has already been resolved")
    return {"id": escalation_id, "status": "resolved"}
