from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    mode: Literal["demo", "live"]


class TranscriptInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    transcript: str = Field(min_length=20, max_length=200000)
    meeting_date: str | None = None
    baseline_id: str | None = None


class Requirement(BaseModel):
    id: str
    description: str
    status: Literal["confirmed", "unclear", "disputed"]
    priority: Literal["must", "should", "could"]
    source_passage: str
    acceptance_criteria: list[str]
    dependencies: list[str] = []
    feasibility: Literal["verified", "unknown", "unsupported"] = "unknown"
    feasibility_evidence: str = ""
    estimate_status: Literal["draft", "reviewed"] = "draft"
    active: bool = True
    version: int = 1


class EstimateTask(BaseModel):
    task: str
    low_hours: float = Field(ge=0)
    likely_hours: float = Field(ge=0)
    high_hours: float = Field(ge=0)
    rationale: str
    assumptions: list[str] = []
    dependencies: list[str] = []
    uncertainty: Literal["low", "medium", "high"]
    reviewer_status: Literal["pending", "approved", "rejected"] = "pending"


class ScopeDocument(BaseModel):
    objective: str
    current_problem: str
    proposed_solution: str
    deliverables: list[str]
    exclusions: list[str]
    assumptions: list[str]
    dependencies: list[str]
    acceptance_criteria: list[str]
    client_responsibilities: list[str]
    open_questions: list[str]
    risks: list[str]


class ScopeResult(BaseModel):
    id: str
    title: str
    mode: Literal["demo", "live"]
    transcript: str
    requirements: list[Requirement]
    estimates: list[EstimateTask]
    scope: ScopeDocument
    proposal: str
    total_low_hours: float
    total_likely_hours: float
    total_high_hours: float
    status: Literal["draft", "approved", "rejected"] = "draft"
    reviewer: str | None = None
    reviewed_at: str | None = None
    baseline_id: str | None = None
    changes: list[dict] = []
    model_id: str | None = None
    prompt_version: str = "scope-template-v1"
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    created_at: str


class ApprovalInput(BaseModel):
    action: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1, max_length=120)
    reason: str = ""
