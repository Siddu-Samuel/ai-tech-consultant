"""Polite, resumable sitemap crawler with a durable JSON checkpoint."""

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from uuid import uuid4

import httpx

from app.chunking import chunk_article
from app.config import get_settings
from app.parser import parse_article
from app.sitemap import ALLOWED_HOST, SitemapEntry, parse_sitemap, validate_source_url

logger = logging.getLogger(__name__)
SITEMAP_URL = "https://support.brilliantdirectories.com/support/sitemap.xml"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_page_url(url: str) -> str:
    safe = validate_source_url(url)
    parts = urlsplit(safe)
    path = parts.path or "/"
    if path != "/" and not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, parts.query, ""))


class Manifest:
    """Atomic file-based ingestion checkpoint, replaceable by PostgreSQL storage later."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {"schema_version": 1, "pages": {}, "runs": []}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("pages"), dict):
                    self.data.update(loaded)
            except (OSError, json.JSONDecodeError):
                logger.exception("Manifest could not be read; starting with an empty checkpoint")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)


class KnowledgeCrawler:
    def __init__(
        self,
        manifest: Manifest,
        *,
        sitemap_url: str = SITEMAP_URL,
        user_agent: str | None = None,
        delay_seconds: float = 1.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
    ):
        self.manifest = manifest
        self.sitemap_url = validate_source_url(sitemap_url)
        self.user_agent = user_agent or "AITechConsultantBot/0.1"
        self.delay_seconds = max(delay_seconds, 0)
        self.max_retries = max(1, max_retries)
        self.client = client
        self._owns_client = client is None
        self._last_request = 0.0
        self._robots: RobotFileParser | None = None

    async def _request(self, url: str, allowed_statuses: frozenset[int] = frozenset()) -> httpx.Response:
        safe_url = validate_source_url(url)
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=5.0),
                follow_redirects=False,
                headers={"User-Agent": self.user_agent},
            )
        error: Exception | None = None
        for attempt in range(self.max_retries):
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.delay_seconds:
                await asyncio.sleep(self.delay_seconds - elapsed)
            self._last_request = time.monotonic()
            try:
                response = await self.client.get(safe_url)
                if response.status_code in allowed_statuses:
                    return response
                if response.is_redirect:
                    target = response.headers.get("location", "")
                    validate_source_url(httpx.URL(safe_url).join(target).human_repr())
                    raise ValueError("Redirects are disabled for source requests")
                response.raise_for_status()
                return response
            except (httpx.HTTPError, ValueError) as exc:
                error = exc
                if attempt + 1 < self.max_retries:
                    await asyncio.sleep(min(0.25 * (2**attempt), 2.0))
        assert error is not None
        raise error

    async def _robots_parser(self) -> RobotFileParser:
        if self._robots is not None:
            return self._robots
        robots_url = f"{urlsplit(self.sitemap_url).scheme}://{ALLOWED_HOST}/robots.txt"
        response = await self._request(robots_url, frozenset({404}))
        parser = RobotFileParser(robots_url)
        if response.status_code == 404:
            parser.parse([])
        else:
            parser.parse(response.text.splitlines())
        self._robots = parser
        return parser

    async def _discover(self, url: str, seen_sitemaps: set[str], pages: dict[str, SitemapEntry]) -> None:
        sitemap_url = validate_source_url(url)
        if sitemap_url in seen_sitemaps:
            return
        seen_sitemaps.add(sitemap_url)
        response = await self._request(sitemap_url)
        is_index, entries = parse_sitemap(response.text)
        for entry in entries:
            safe_entry = validate_source_url(entry.url)
            if is_index:
                await self._discover(safe_entry, seen_sitemaps, pages)
            else:
                canonical = canonical_page_url(safe_entry)
                pages.setdefault(canonical, SitemapEntry(canonical, entry.lastmod))

    async def run(self, max_pages: int | None = None) -> dict[str, Any]:
        run_id = str(uuid4())
        run: dict[str, Any] = {
            "run_id": run_id,
            "started_at": _now(),
            "finished_at": None,
            "status": "running",
            "discovered": 0,
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "removed": 0,
            "failed": 0,
            "errors": [],
        }
        self.manifest.data.setdefault("runs", []).append(run)
        self.manifest.save()
        try:
            robots = await self._robots_parser()
            if not robots.can_fetch(self.user_agent, self.sitemap_url):
                raise PermissionError("robots.txt disallows access to the configured sitemap")
            pages: dict[str, SitemapEntry] = {}
            await self._discover(self.sitemap_url, set(), pages)
            if max_pages is not None:
                if max_pages < 1:
                    raise ValueError("max_pages must be at least 1")
                pages = dict(list(pages.items())[:max_pages])
            run["discovered"] = len(pages)

            active_before = {
                url for url, page in self.manifest.data["pages"].items() if page.get("status") == "active"
            }
            for url, entry in pages.items():
                try:
                    if not robots.can_fetch(self.user_agent, url):
                        raise PermissionError("robots.txt disallows this article")
                    response = await self._request(url)
                    article = parse_article(response.text, url)
                    safe_images = []
                    for image in article.images:
                        try:
                            validate_source_url(image.url)
                        except ValueError:
                            continue
                        safe_images.append(image)
                    article = article.__class__(article.title, article.text, article.sections, safe_images)
                    digest = sha256(
                        json.dumps(
                            {"title": article.title, "text": article.text, "images": [i.url for i in safe_images]},
                            sort_keys=True,
                            ensure_ascii=False,
                        ).encode("utf-8")
                    ).hexdigest()
                    prior = self.manifest.data["pages"].get(url, {})
                    if prior.get("content_hash") == digest and prior.get("status") == "active":
                        run["unchanged"] += 1
                        prior.update({"lastmod": entry.lastmod, "last_checked_at": _now(), "attempts": 0, "last_error": None})
                    else:
                        article_id = prior.get("article_id") or sha256(url.encode()).hexdigest()[:24]
                        chunks = chunk_article(article, article_id)
                        self.manifest.data["pages"][url] = {
                            "article_id": article_id,
                            "url": url,
                            "title": article.title,
                            "text": article.text,
                            "sections": [{"heading": x.heading, "content": x.content} for x in article.sections],
                            "images": [i.__dict__ for i in safe_images],
                            "chunks": [chunk.__dict__ for chunk in chunks],
                            "content_hash": digest,
                            "lastmod": entry.lastmod,
                            "last_ingested_at": _now(),
                            "last_checked_at": _now(),
                            "attempts": 0,
                            "last_error": None,
                            "status": "active",
                        }
                        run["created" if not prior else "updated"] += 1
                    self.manifest.save()
                except Exception as exc:  # isolate failures per page so one bad URL cannot stop ingestion
                    prior = self.manifest.data["pages"].setdefault(url, {"url": url})
                    prior.update({"status": "failed", "attempts": prior.get("attempts", 0) + 1, "last_error": str(exc), "retry_after": _now()})
                    run["failed"] += 1
                    run["errors"].append(f"{url}: {type(exc).__name__}")
                    self.manifest.save()
            current = set(pages)
            if max_pages is None:
                for removed_url in active_before - current:
                    self.manifest.data["pages"][removed_url]["status"] = "removed"
                    self.manifest.data["pages"][removed_url]["removed_at"] = _now()
                    run["removed"] += 1
            run["status"] = "completed_with_errors" if run["failed"] else "completed"
        except Exception as exc:
            run["status"] = "failed"
            run["errors"].append(f"run: {type(exc).__name__}: {exc}")
        finally:
            run["finished_at"] = _now()
            self.manifest.save()
            if self._owns_client and self.client is not None:
                await self.client.aclose()
                self.client = None
        return run


def manifest_status(manifest: Manifest) -> dict[str, Any]:
    pages = manifest.data.get("pages", {})
    latest = manifest.data.get("runs", [])
    counts = {status: sum(page.get("status") == status for page in pages.values()) for status in ("active", "removed", "failed")}
    return {"latest_run": latest[-1] if latest else None, "pages": counts}


async def _run_cli(max_pages: int | None) -> None:
    settings = get_settings()
    from app.database import KnowledgeStore
    from app.embeddings import create_embedder
    from app.image_analysis import analyze_manifest_images
    from app.indexing import index_manifest

    store = KnowledgeStore(settings.database_url, settings.embedding_dimensions, settings.embedding_provider)
    store.initialize()
    lease = store.acquire_ingestion_lease()
    if not lease.acquired:
        raise RuntimeError("Another ingestion worker already holds the database lease")
    try:
        crawler = KnowledgeCrawler(
            Manifest(settings.crawl_manifest_path),
            user_agent=settings.crawl_user_agent,
            delay_seconds=settings.crawl_delay_seconds,
            max_retries=settings.crawl_max_retries,
        )
        result = await crawler.run(max_pages)
        if result["status"] in {"completed", "completed_with_errors"}:
            image_result = await analyze_manifest_images(crawler.manifest.data, settings)
            crawler.manifest.save()
            index_result = await index_manifest(
                crawler.manifest.data,
                store,
                create_embedder(settings),
                model_label=settings.embedding_model or settings.embedding_provider,
                dimensions=settings.embedding_dimensions,
            )
            result["image_analysis"] = image_result
            result["indexing"] = index_result
        crawler.manifest.data["runs"][-1].update(result)
        crawler.manifest.save()
        store.sync_ingestion(crawler.manifest.data)
        print(json.dumps(result, indent=2))
    finally:
        lease.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Incrementally ingest the configured help-center sitemap")
    parser.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(_run_cli(args.max_pages))
