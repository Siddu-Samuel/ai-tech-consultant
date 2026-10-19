import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pipeline import _check_feasibility, _demo_analysis, _document, _estimate, _mark_contradictions, _passages
from app.schemas import EstimateTask, Requirement, ScopeDocument, ScopeResult
from app.store import put_scope, review_scope

ROOT = Path(__file__).resolve().parents[2]
CASES = [json.loads(line) for line in (ROOT / "evals" / "scope_cases.jsonl").read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_scope_evaluation_cases(case):
    requirements = _demo_analysis(case["title"], case["transcript"])
    expected = case["expected"]
    assert len(requirements) >= expected.get("requirements_min", 0)
    assert all(r.source_passage and r.source_passage in case["transcript"] for r in requirements)
    estimates = _estimate(requirements)
    assert all(0 <= task.low_hours <= task.likely_hours <= task.high_hours for task in estimates)
    scope, proposal = _document(case["title"], requirements, estimates)
    assert "not a fixed price" in proposal
    assert all(section.casefold() in proposal.casefold() for section in ["Milestones", "Client responsibilities", "Risks", "Acceptance criteria"])
    assert any("unverified product capabilities" in item.lower() for item in scope.exclusions)
    if expected.get("unclear_requirement"):
        assert any(r.status == "unclear" for r in requirements)
    if expected.get("open_question"):
        assert scope.open_questions or any(r.status == "unclear" for r in requirements)


def test_three_transcript_fixtures_cover_meeting_a_b_c_followup():
    fixtures = [ROOT / "evals" / name for name in ["meeting_a_search_filters.txt", "meeting_b_checkout_notifications.txt", "meeting_c_followup_scope_change.txt"]]
    assert all(path.is_file() and "Client:" in path.read_text(encoding="utf-8") for path in fixtures)
    meeting_c = fixtures[2].read_text(encoding="utf-8")
    assert all(word in meeting_c.lower() for word in ["add", "remove", "change", "campaign"])


def test_oversized_single_speaker_turn_is_split_with_timestamp_context():
    chunks = _passages("[00:42] Client: " + ("long customer requirement " * 250))
    assert len(chunks) > 1
    assert all(len(chunk) <= 1800 and chunk.startswith("[00:42] Client:") for chunk in chunks)


def test_opposing_requirements_are_marked_disputed():
    requirements = _demo_analysis("Contradiction", "Client: Include an empty-results message.\nClient: Do not include an empty-results message.")
    checked = _mark_contradictions(requirements)
    assert len(checked) == 2
    assert all(item.status == "disputed" for item in checked)


def test_generated_estimates_and_proposal_keep_unknowns_open():
    requirements = [Requirement(id="REQ-001", description="Integrate chosen provider", status="unclear", priority="should", source_passage="provider not chosen", acceptance_criteria=["Confirm provider"])]
    estimate = _estimate(requirements)
    scope, proposal = _document("Payments", requirements, estimate)
    assert scope.open_questions
    assert all("delivery date" not in task.task.lower() for task in estimate)
    assert "not a fixed price" in proposal


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "meeting-to-scope"


def test_production_rejects_ephemeral_scope_storage():
    from pydantic import ValidationError
    from app.config import Settings

    with pytest.raises(ValidationError, match="Production requires STORAGE_MODE=postgres"):
        Settings(app_env="production", storage_mode="sqlite")


def test_feasibility_calls_only_task1_http_and_keeps_unknown_when_no_evidence(monkeypatch):
    import app.pipeline as pipeline

    calls = []

    class Response:
        def __init__(self, body): self.body = body
        def raise_for_status(self): return None
        def json(self): return self.body

    class Client:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response({"status": "insufficient_evidence", "answer": "Needs investigation", "sources": []})

    monkeypatch.setattr(pipeline.httpx, "AsyncClient", Client)
    requirements = [Requirement(id="REQ-1", description="Can the platform do something?", status="unclear", priority="should", source_passage="client asked", acceptance_criteria=["verify"]) ]
    result = __import__("asyncio").run(_check_feasibility(requirements))
    assert calls and calls[0][0].endswith("/query")
    assert result[0].feasibility == "unknown"
    assert "insufficient evidence" in result[0].feasibility_evidence


def test_followup_diff_uses_approved_baseline_and_flags_additions():
    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    scope_document = ScopeDocument(objective="Search", current_problem="", proposed_solution="", deliverables=[], exclusions=[], assumptions=[], dependencies=[], acceptance_criteria=[], client_responsibilities=[], open_questions=[], risks=[])
    estimates = [EstimateTask(task="Discovery", low_hours=1, likely_hours=2, high_hours=3, rationale="Review", uncertainty="medium")]
    baseline = ScopeResult(id=str(uuid.uuid4()), title="Search follow-up test", mode="demo", transcript="Meeting A", requirements=[
        Requirement(id="REQ-001", description="Filter controls work on mobile", status="confirmed", priority="should", source_passage="mobile", acceptance_criteria=["works"]),
        Requirement(id="REQ-002", description="Include an empty-results message", status="confirmed", priority="should", source_passage="empty results", acceptance_criteria=["shows"]),
        Requirement(id="REQ-003", description="Filter listings by location", status="confirmed", priority="should", source_passage="location", acceptance_criteria=["filters"]),
    ], estimates=estimates, scope=scope_document, proposal="draft", total_low_hours=1, total_likely_hours=2, total_high_hours=3, created_at=now)
    put_scope(baseline)
    review_scope(baseline.id, True, "baseline reviewer")
    revision = ScopeResult(id=str(uuid.uuid4()), title=baseline.title, mode="demo", transcript="Meeting C", requirements=[
        Requirement(id="REQ-001", description="Filters need to work on mobile and tablets", status="confirmed", priority="must", source_passage="change mobile", acceptance_criteria=["works on tablets"]),
        Requirement(id="REQ-002", description="Remove the empty-results message", status="confirmed", priority="should", source_passage="remove empty-results message", acceptance_criteria=["existing behavior"]),
        Requirement(id="REQ-003", description="Add a service-area filter", status="confirmed", priority="should", source_passage="add service-area filter", acceptance_criteria=["filters area"]),
    ], estimates=estimates, scope=scope_document, proposal="draft", total_low_hours=1, total_likely_hours=2, total_high_hours=3, baseline_id=baseline.id, created_at=now)
    result = put_scope(revision)
    kinds = {change["type"] for change in result.changes}
    assert {"addition", "removal", "modification"}.issubset(kinds)
    addition = next(change for change in result.changes if change["type"] == "addition")
    assert addition["potential_out_of_scope"] is True
    assert result.status == "draft"  # Revision cannot become a baseline before review.
