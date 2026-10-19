"""Heading-aware text chunking with stable identifiers."""

from dataclasses import dataclass
from hashlib import sha256

from app.parser import ParsedArticle


@dataclass(frozen=True)
class ArticleChunk:
    chunk_id: str
    section_heading: str
    content: str
    image_urls: tuple[str, ...]


def chunk_article(article: ParsedArticle, article_id: str, max_chars: int = 1400, overlap: int = 160) -> list[ArticleChunk]:
    if max_chars < 100 or overlap < 0 or overlap >= max_chars:
        raise ValueError("Chunk size must be >=100 and overlap must be between 0 and chunk size")
    image_map: dict[str, list[str]] = {}
    for image in article.images:
        image_map.setdefault(image.section_heading, []).append(image.url)

    chunks: list[ArticleChunk] = []
    for section in article.sections:
        text = f"{section.heading}\n{section.content}".strip()
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            if end < len(text):
                boundary = text.rfind("\n", start + max_chars // 2, end)
                if boundary > start:
                    end = boundary
            content = text[start:end].strip()
            digest = sha256(f"{article_id}\n{section.heading}\n{start}\n{content}".encode()).hexdigest()[:20]
            chunks.append(ArticleChunk(digest, section.heading, content, tuple(image_map.get(section.heading, []))))
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return chunks
