"""Article extraction that preserves section order and image context."""

from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class ParsedImage:
    url: str
    alt_text: str
    section_heading: str
    nearby_context: str


@dataclass(frozen=True)
class ParsedSection:
    heading: str
    content: str


@dataclass(frozen=True)
class ParsedArticle:
    title: str
    text: str
    sections: list[ParsedSection]
    images: list[ParsedImage]


REMOVE_SELECTORS = "nav, header, footer, aside, script, style, noscript, form, [role=navigation], .cookie-banner, .sidebar"
MAIN_SELECTORS = ("main", "article", "#content", ".article-content", ".post-content", "body")


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def parse_article(html: str, page_url: str) -> ParsedArticle:
    soup = BeautifulSoup(html, "lxml")
    title = _clean_text((soup.title.get_text(" ", strip=True) if soup.title else ""))
    for node in soup.select(REMOVE_SELECTORS):
        node.decompose()

    main: Tag | None = None
    for selector in MAIN_SELECTORS:
        found = soup.select_one(selector)
        if found is not None and _clean_text(found.get_text(" ", strip=True)):
            main = found
            break
    if main is None:
        raise ValueError("No readable article content found")

    sections: list[ParsedSection] = []
    current_heading = title or "Overview"
    content_lines: list[str] = []
    all_text: list[str] = []
    image_records: list[ParsedImage] = []
    for element in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "tr", "img"], recursive=True):
        if not isinstance(element, Tag):
            continue
        if element.name in {"h1", "h2", "h3", "h4"}:
            if content_lines:
                sections.append(ParsedSection(current_heading, "\n".join(content_lines)))
                content_lines = []
            current_heading = _clean_text(element.get_text(" ", strip=True)) or current_heading
            continue
        if element.name == "img":
            raw_src = element.get("src") or element.get("data-src")
            if isinstance(raw_src, str) and raw_src.strip():
                parent = element.parent
                nearby = _clean_text(parent.get_text(" ", strip=True)) if isinstance(parent, Tag) else ""
                image_records.append(
                    ParsedImage(
                        url=urljoin(page_url, raw_src.strip()),
                        alt_text=_clean_text(str(element.get("alt") or "")),
                        section_heading=current_heading,
                        nearby_context=nearby,
                    )
                )
            continue
        line = _clean_text(element.get_text(" ", strip=True))
        if line and (not content_lines or line != content_lines[-1]):
            content_lines.append(line)
            all_text.append(line)
    if content_lines:
        sections.append(ParsedSection(current_heading, "\n".join(content_lines)))
    if not sections:
        raise ValueError("No readable article text found")
    deduped_images = list({item.url: item for item in image_records}.values())
    return ParsedArticle(title=title, text="\n".join(all_text), sections=sections, images=deduped_images)
