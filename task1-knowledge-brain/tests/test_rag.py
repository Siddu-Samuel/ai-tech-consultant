import asyncio
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.answering import ExtractiveTestAnswerer, validate_citations
from app.database import KnowledgeStore
from app.embeddings import LocalTestEmbedder
from app.image_analysis import detect_image_type, fetch_image
from app.indexing import index_manifest
from app.main import app, settings
from app.retrieval import retrieve


def make_manifest(status: str = "active") -> dict:
    text = "To configure profile filters, open the search settings and choose which filters to display."
    return {
        "pages": {
            "https://support.brilliantdirectories.com/support/search/": {
                "article_id": "article-search",
                "url": "https://support.brilliantdirectories.com/support/search/",
                "title": "Configure profile filters",
                "content_hash": "content-v1",
                "lastmod": "2026-01-01",
                "status": status,
                "last_ingested_at": "2026-01-01T00:00:00+00:00",
                "chunks": [{"chunk_id": "chunk-search", "section_heading": "Search", "content": text, "image_urls": []}],
                "images": [],
            }
        },
        "runs": [],
    }


class KnowledgeStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = KnowledgeStore("sqlite:///:memory:", embedding_dimensions=64)
        self.store.initialize()

    def tearDown(self) -> None:
        self.store.close()

    def test_manifest_index_and_retrieval_return_active_source(self) -> None:
        async def execute() -> list[dict]:
            result = await index_manifest(make_manifest(), self.store, LocalTestEmbedder(64), model_label="local-test", dimensions=64)
            self.assertEqual(result["embedded"], 1)
            return await retrieve("How do I configure profile filters?", self.store, LocalTestEmbedder(64))

        matches = asyncio.run(execute())
        self.assertEqual(matches[0]["chunk_id"], "chunk-search")
        self.assertEqual(matches[0]["url"], "https://support.brilliantdirectories.com/support/search/")

    def test_removed_article_is_never_retrieved(self) -> None:
        self.store.sync_manifest(make_manifest(status="removed"))
        self.assertEqual(self.store.search_chunks([0.0] * 64, 6), [])

    def test_indexing_reuses_vectors_when_text_and_configuration_are_unchanged(self) -> None:
        async def execute() -> tuple[dict, dict]:
            manifest = make_manifest()
            first = await index_manifest(manifest, self.store, LocalTestEmbedder(64), model_label="local-test", dimensions=64)
            second = await index_manifest(manifest, self.store, LocalTestEmbedder(64), model_label="local-test", dimensions=64)
            return first, second

        first, second = asyncio.run(execute())
        self.assertEqual(first["embedded"], 1)
        self.assertEqual(second["reused"], 1)

    def test_escalation_resolution_is_idempotent_and_persists_approved_answer(self) -> None:
        escalation_id = self.store.create_escalation("Unknown product question", "No evidence", [], "request-123456")
        vector = [0.0] * 64
        self.assertTrue(self.store.resolve_escalation(escalation_id, "Reviewed answer", "reviewer-1", "customer", "customer-7", vector))
        self.assertFalse(self.store.resolve_escalation(escalation_id, "Second answer", "reviewer-2", "global", None, vector))
        record = self.store.list_escalations(include_resolved=True)[0]
        self.assertEqual(record["status"], "resolved")
        self.assertEqual(record["reviewer"], "reviewer-1")
        approved = self.store._sqlite.execute("SELECT scope,customer_id,answer FROM approved_knowledge").fetchone()
        self.assertEqual(tuple(approved), ("customer", "customer-7", "Reviewed answer"))

    def test_ingestion_lease_prevents_overlapping_workers(self) -> None:
        first = self.store.acquire_ingestion_lease()
        second = self.store.acquire_ingestion_lease()
        self.assertTrue(first.acquired)
        self.assertFalse(second.acquired)
        first.release()
        third = self.store.acquire_ingestion_lease()
        self.assertTrue(third.acquired)
        third.release()

    def test_customer_approved_knowledge_is_scoped_and_cites_active_provenance(self) -> None:
        from app.embeddings import embed_local_test
        from app.retrieval import retrieve

        self.store.sync_manifest(make_manifest())
        source = {"title": "Configure profile filters", "url": "https://support.brilliantdirectories.com/support/search/", "chunk_id": "chunk-search"}
        escalation_id = self.store.create_escalation("Unknown profile setting", "No answer", [source], "request-scope-123")
        answer = "The reviewed example uses the saved profile-filter preset."
        self.store.resolve_escalation(escalation_id, answer, "reviewer-1", "customer", "customer-7", embed_local_test(answer, 64))

        async def execute(customer_id: str | None) -> list[dict]:
            return await retrieve("What is the reviewed profile filter preset?", self.store, LocalTestEmbedder(64), customer_id=customer_id)

        customer_matches = asyncio.run(execute("customer-7"))
        other_matches = asyncio.run(execute("customer-8"))
        anonymous_matches = asyncio.run(execute(None))
        self.assertTrue(any(item.get("metadata", {}).get("approved_knowledge") for item in customer_matches))
        self.assertFalse(any(item.get("metadata", {}).get("approved_knowledge") for item in other_matches))
        self.assertFalse(any(item.get("metadata", {}).get("approved_knowledge") for item in anonymous_matches))
        approved_item = next(item for item in customer_matches if item.get("metadata", {}).get("approved_knowledge"))
        self.assertEqual(approved_item["chunk_id"], f"approved:approved:{escalation_id}")
        self.assertEqual(approved_item["url"], source["url"])


class CitationAndApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = KnowledgeStore("sqlite:///:memory:", 64)
        self.store.initialize()
        self.manifest = make_manifest()
        asyncio.run(index_manifest(self.manifest, self.store, LocalTestEmbedder(64), model_label="local-test", dimensions=64))

    def tearDown(self) -> None:
        self.store.close()

    def test_citations_are_restricted_to_retrieved_chunks(self) -> None:
        evidence = [{"chunk_id": "valid", "title": "T", "url": "https://example.test/a"}]
        self.assertEqual(validate_citations(["forged", "valid", "valid"], evidence), [{"title": "T", "url": "https://example.test/a", "chunk_id": "valid"}])

    def test_query_returns_source_grounded_demo_answer_and_unknown_escalates(self) -> None:
        embedder = LocalTestEmbedder(64)
        old_env, old_key = settings.app_env, settings.anthropic_api_key
        settings.app_env, settings.anthropic_api_key = "test", ""
        try:
            with patch("app.main.get_store", return_value=self.store), patch("app.main.get_embedder", return_value=embedder), patch("app.main.get_answer_generator", return_value=ExtractiveTestAnswerer()):
                client = TestClient(app)
                answered = client.post("/query", json={"question": "How do I configure profile filters?"}, headers={"X-Request-ID": "task2-case-123"})
                self.assertEqual(answered.status_code, 200)
                body = answered.json()
                self.assertEqual(body["status"], "answered")
                self.assertEqual(body["mode"], "demo")
                self.assertEqual(body["sources"][0]["chunk_id"], "chunk-search")
                self.assertEqual(body["request_id"], "task2-case-123")
                unknown = client.post("/query", json={"question": "What color is the moon?"})
                self.assertEqual(unknown.status_code, 200)
                self.assertEqual(unknown.json()["status"], "insufficient_evidence", unknown.json())
                self.assertTrue(unknown.json()["needs_human"])
                self.assertIsNotNone(unknown.json()["escalation_id"])
                audits = self.store._sqlite.execute("SELECT status,question_hash,input_tokens FROM query_audits ORDER BY created_at").fetchall()
                self.assertEqual(len(audits), 2)
                self.assertEqual({row[0] for row in audits}, {"answered", "invalid_citation"})
                self.assertEqual(len(audits[0][1]), 64)
                self.assertIsNone(audits[0][2])
        finally:
            settings.app_env, settings.anthropic_api_key = old_env, old_key

    def test_query_rejects_malformed_question(self) -> None:
        with patch("app.main.get_store", return_value=self.store):
            response = TestClient(app).post("/query", json={"question": "x"})
        self.assertEqual(response.status_code, 422)

    def test_customer_scoped_query_requires_service_token(self) -> None:
        old_token = settings.task1_service_token
        settings.task1_service_token = "service-secret"
        try:
            with patch("app.main.get_store", return_value=self.store):
                client = TestClient(app)
                denied = client.post("/query", json={"question": "Can I use profile filters?", "customer_id": "customer-7"})
                accepted = client.post(
                    "/query",
                    json={"question": "Can I use profile filters?", "customer_id": "customer-7"},
                    headers={"X-Service-Token": "service-secret"},
                )
            self.assertEqual(denied.status_code, 401)
            self.assertEqual(accepted.status_code, 200)
        finally:
            settings.task1_service_token = old_token

    def test_answer_includes_linked_image_description_and_review_status(self) -> None:
        url = "https://support.brilliantdirectories.com/support/search.png"
        image_manifest = make_manifest()
        page = next(iter(image_manifest["pages"].values()))
        page["chunks"][0]["image_urls"] = [url]
        page["images"] = [{
            "url": url,
            "section_heading": "Search",
            "alt_text": "Search filter panel",
            "nearby_context": "Set profile filters",
            "description": "The screenshot appears to show the Profile Filter checkbox.",
            "analysis_status": "uncertain",
            "content_hash": "image-hash",
        }]
        asyncio.run(index_manifest(image_manifest, self.store, LocalTestEmbedder(64), model_label="local-test", dimensions=64))
        old_env, old_key = settings.app_env, settings.anthropic_api_key
        settings.app_env, settings.anthropic_api_key = "test", ""
        try:
            with patch("app.main.get_store", return_value=self.store), patch("app.main.get_embedder", return_value=LocalTestEmbedder(64)), patch("app.main.get_answer_generator", return_value=ExtractiveTestAnswerer()):
                response = TestClient(app).post("/query", json={"question": "How do I configure profile filters?"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["image_references"][0]["description"], "The screenshot appears to show the Profile Filter checkbox.")
            self.assertEqual(response.json()["image_references"][0]["analysis_status"], "uncertain")
        finally:
            settings.app_env, settings.anthropic_api_key = old_env, old_key


class ImageSafetyTests(unittest.TestCase):
    def test_image_type_detection_accepts_supported_signatures(self) -> None:
        self.assertEqual(detect_image_type(b"\x89PNG\r\n\x1a\nrest"), "image/png")
        self.assertEqual(detect_image_type(b"\xff\xd8\xffrest"), "image/jpeg")
        self.assertEqual(detect_image_type(b"RIFFxxxxWEBPrest"), "image/webp")

    def test_unsupported_image_format_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            detect_image_type(b"<svg xmlns='http://www.w3.org/2000/svg'/>")

    def test_failed_download_and_external_host_are_rejected(self) -> None:
        async def execute() -> None:
            client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(404)))
            try:
                with self.assertRaises(httpx.HTTPStatusError):
                    await fetch_image("https://support.brilliantdirectories.com/image.png", client)
                with self.assertRaises(ValueError):
                    await fetch_image("https://127.0.0.1/image.png", client)
            finally:
                await client.aclose()

        asyncio.run(execute())


if __name__ == "__main__":
    unittest.main()
