import unittest

from app.answering import validate_citations
from app.retrieval import has_conflicting_evidence


class EvidencePolicyTests(unittest.TestCase):
    def test_conflicting_supported_and_unsupported_claims_require_review(self) -> None:
        evidence = [
            {"content": "Profile filters can be enabled from search settings."},
            {"content": "Profile filters cannot be enabled on this layout."},
        ]
        self.assertTrue(has_conflicting_evidence("Can profile filters be enabled?", evidence))

    def test_consistent_evidence_is_not_flagged(self) -> None:
        evidence = [
            {"content": "Profile filters can be enabled from search settings."},
            {"content": "Search filters are available in the admin settings."},
        ]
        self.assertFalse(has_conflicting_evidence("Can profile filters be enabled?", evidence))

    def test_unretrieved_citations_are_dropped(self) -> None:
        evidence = [{"chunk_id": "actual", "title": "Help", "url": "https://support.brilliantdirectories.com/help/"}]
        result = validate_citations(["invented", "actual"], evidence)
        self.assertEqual([item["chunk_id"] for item in result], ["actual"])


if __name__ == "__main__":
    unittest.main()
