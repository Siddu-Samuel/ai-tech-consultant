"""Safe parsing helpers for sitemap documents."""

from dataclasses import dataclass
from urllib.parse import urlsplit
from xml.etree import ElementTree

ALLOWED_HOST = "support.brilliantdirectories.com"
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass(frozen=True)
class SitemapEntry:
    url: str
    lastmod: str | None = None


def validate_source_url(url: str, allowed_host: str = ALLOWED_HOST) -> str:
    """Return a canonical HTTPS URL restricted to the approved source host."""
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() != "https" or parsed.hostname is None:
        raise ValueError("Only absolute HTTPS source URLs are allowed")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Credentials and non-standard ports are not allowed")
    host = parsed.hostname.lower().rstrip(".")
    if host != allowed_host.lower():
        raise ValueError("URL host is outside the configured knowledge source")
    if parsed.fragment:
        parsed = parsed._replace(fragment="")
    return parsed.geturl()


def parse_sitemap(xml_text: str) -> tuple[bool, list[SitemapEntry]]:
    """Return whether this is an index and its nested sitemap or URL entries."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise ValueError("Invalid sitemap XML") from exc

    kind = root.tag.rsplit("}", 1)[-1]
    if kind not in {"urlset", "sitemapindex"}:
        raise ValueError("Document is not a sitemap or sitemap index")

    child_name = "sitemap" if kind == "sitemapindex" else "url"
    entries: list[SitemapEntry] = []
    for node in root.findall(f"{SITEMAP_NS}{child_name}"):
        location = node.findtext(f"{SITEMAP_NS}loc")
        if not location:
            continue
        lastmod = node.findtext(f"{SITEMAP_NS}lastmod")
        entries.append(SitemapEntry(url=location.strip(), lastmod=lastmod.strip() if lastmod else None))
    return kind == "sitemapindex", entries
