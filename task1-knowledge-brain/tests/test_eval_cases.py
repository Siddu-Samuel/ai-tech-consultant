"""Twenty grounded retrieval-policy regression cases, separate from provider evals."""
import json
from pathlib import Path

from app.retrieval import has_conflicting_evidence, keyword_score

ROOT = Path(__file__).resolve().parents[2]
CASES = [json.loads(line) for line in (ROOT / "evals" / "knowledge_cases.jsonl").read_text(encoding="utf-8").splitlines()]


def test_knowledge_eval_dataset_has_twenty_cases():
    assert len(CASES) >= 20
    assert len({case["id"] for case in CASES}) == len(CASES)


def test_answerable_cases_have_relevant_evidence():
    for case in CASES:
        if case["expected"] == "answered":
            assert keyword_score(case["question"], case["evidence"]) >= 0.3, case["id"]


def test_conflict_case_is_detected_and_unknown_queries_are_not_claimed_as_supported():
    for case in CASES:
        evidence = [{"content": case["evidence"]}]
        if case["expected"] == "conflict":
            assert has_conflicting_evidence(case["question"], evidence), case["id"]
        if case["expected"] == "unknown":
            assert any(marker in case["evidence"].casefold() for marker in ["not published", "does not document", "not available", "not stated", "no booking"]), case["id"]
