"""Shared API envelope schemas; feature schemas are added in later phases."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    mode: Literal["demo", "live"]


class IngestionRequest(BaseModel):
    max_pages: int | None = Field(default=None, ge=1, le=500)


class IngestionStatusResponse(BaseModel):
    run_id: str | None
    status: str
    discovered: int
    created: int
    updated: int
    unchanged: int
    removed: int
    failed: int
    errors: list[str]


class SourceCitation(BaseModel):
    title: str
    url: str
    chunk_id: str


class ImageReference(BaseModel):
    url: str
    alt_text: str = ""
    description: str = ""
    analysis_status: str = "pending"


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    context: str | None = Field(default=None, max_length=4000)
    customer_id: str | None = Field(default=None, max_length=120)


class QueryResponse(BaseModel):
    answer: str
    status: Literal["answered", "insufficient_evidence"]
    sources: list[SourceCitation]
    image_references: list[ImageReference]
    needs_human: bool
    escalation_id: str | None
    request_id: str
    mode: Literal["demo", "live"]
    model: str | None = None


class EscalationCreateRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    reason: str = Field(min_length=3, max_length=1000)
    evidence: list[dict[str, object]] = Field(default_factory=list, max_length=20)
    request_id: str = Field(min_length=8, max_length=120)


class EscalationResolveRequest(BaseModel):
    answer: str = Field(min_length=3, max_length=8000)
    reviewer: str = Field(min_length=1, max_length=120)
    scope: Literal["global", "customer"] = "global"
    customer_id: str | None = Field(default=None, max_length=120)
    expires_at: str | None = None
