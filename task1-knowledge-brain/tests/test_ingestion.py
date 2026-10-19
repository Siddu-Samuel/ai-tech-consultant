import asyncio
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import httpx

from app.chunking import chunk_article
from app.crawler import KnowledgeCrawler, Manifest
from app.parser import parse_article
from app.sitemap import parse_sitemap, validate_source_url


HOST = "support.brilliantdirectories.com"
ROOT = f"https://{HOST}/support/sitemap.xml"


class SitemapTests(unittest.TestCase):
    def test_parses_index_and_lastmod(self) -> None:
        xml = f'''<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>https://{HOST}/support/part.xml</loc><lastmod>2026-01-02</lastmod></sitemap>
        </sitemapindex>'''
        is_index, entries = parse_sitemap(xml)
        self.assertTrue(is_index)
        self.assertEqual(entries[0].lastmod, "2026-01-02")

    def test_rejects_non_source_and_non_https_urls(self) -> None:
        for url in ("http://support.brilliantdirectories.com/a", "https://127.0.0.1/a", "https://evil.example/a"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_source_url(url)


class ArticleParsingTests(unittest.TestCase):
    def test_extracts_ordered_sections_and_deduplicated_images(self) -> None:
        html = '''<html><head><title>Search help</title></head><body>
        <nav>ignore this navigation</nav><main><h1>Search</h1><p>Open search settings.</p>
        <img src="/assets/search.png" alt="Search settings screen">
        <h2>Filters</h2><ul><li>Choose a filter.</li></ul>
        <img src="/assets/search.png" alt="duplicate"></main></body></html>'''
        article = parse_article(html, f"https://{HOST}/support/search")
        self.assertEqual(article.title, "Search help")
        self.assertEqual([section.heading for section in article.sections], ["Search", "Filters"])
        self.assertNotIn("ignore this navigation", article.text)
        self.assertEqual(len(article.images), 1)
        self.assertEqual(article.images[0].url, f"https://{HOST}/assets/search.png")

    def test_rejects_empty_article(self) -> None:
        with self.assertRaises(ValueError):
            parse_article("<html><body><nav>only navigation</nav></body></html>", f"https://{HOST}/support/empty")

    def test_chunking_is_stable_and_heading_aware(self) -> None:
        article = parse_article(
            "<main><h2>Setup</h2><p>" + ("Configure the profile and select a setting. " * 12) + "</p></main>",
            f"https://{HOST}/support/setup",
        )
        one = chunk_article(article, "article-1", max_chars=160, overlap=20)
        two = chunk_article(article, "article-1", max_chars=160, overlap=20)
        self.assertGreater(len(one), 1)
        self.assertEqual([chunk.chunk_id for chunk in one], [chunk.chunk_id for chunk in two])
        self.assertTrue(all(chunk.section_heading == "Setup" for chunk in one))


class CrawlerTests(unittest.TestCase):
    def test_incremental_manifest_skips_unchanged_and_marks_removed(self) -> None:
        included = {"article-a": True, "article-b": True}
        manifest_path = Path(tempfile.gettempdir()) / f"manifest-test-{uuid4()}.json"

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if path == "/support/sitemap.xml":
                return httpx.Response(200, text=f'''<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                <sitemap><loc>https://{HOST}/support/nested.xml</loc></sitemap></sitemapindex>''')
            if path == "/support/nested.xml":
                urls = "".join(
                    f"<url><loc>https://{HOST}/support/{name}/</loc><lastmod>2026-01-01</lastmod></url>"
                    for name, present in included.items() if present
                )
                return httpx.Response(200, text=f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
            if path.endswith("/article-a/") or path.endswith("/article-b/"):
                name = path.split("/")[-2]
                return httpx.Response(200, text=f"<html><head><title>{name}</title></head><body><main><p>Content for {name}</p></main></body></html>")
            return httpx.Response(404)

        async def execute() -> tuple[dict, dict, dict]:
            manifest_path.unlink(missing_ok=True)
            try:
                client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
                crawler = KnowledgeCrawler(Manifest(manifest_path), sitemap_url=ROOT, delay_seconds=0, max_retries=1, client=client)
                first = await crawler.run()
                second = await crawler.run()
                included["article-b"] = False
                third = await crawler.run()
                await client.aclose()
                return first, second, third
            finally:
                manifest_path.unlink(missing_ok=True)

        first, second, third = asyncio.run(execute())
        self.assertEqual((first["created"], first["discovered"]), (2, 2))
        self.assertEqual(second["unchanged"], 2)
        self.assertEqual((third["removed"], third["discovered"]), (1, 1))

    def test_page_failure_does_not_abort_run(self) -> None:
        manifest_path = Path(tempfile.gettempdir()) / f"manifest-failure-test-{uuid4()}.json"
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if request.url.path == "/support/sitemap.xml":
                return httpx.Response(200, text=f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://{HOST}/support/fail/</loc></url></urlset>')
            return httpx.Response(503)

        async def execute() -> dict:
            manifest_path.unlink(missing_ok=True)
            try:
                client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
                result = await KnowledgeCrawler(Manifest(manifest_path), sitemap_url=ROOT, delay_seconds=0, max_retries=1, client=client).run()
                await client.aclose()
                return result
            finally:
                manifest_path.unlink(missing_ok=True)

        result = asyncio.run(execute())
        self.assertEqual(result["status"], "completed_with_errors")
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["discovered"], 1)


if __name__ == "__main__":
    unittest.main()
