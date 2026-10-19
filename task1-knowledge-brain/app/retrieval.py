"""Vector/keyword retrieval with active-page filtering and source metadata."""

import math
import re
from typing import Any

from app.database import KnowledgeStore
from app.embeddings import Embedder

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "do", "does", "for", "from",
    "how", "i", "in", "is", "it", "of", "on", "or", "should", "the", "to", "was", "what", "when",
    "where", "which", "who", "why", "with", "would", "you", "your",
}


def content_terms(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.casefold()) if word not in STOPWORDS}


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norms = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
    return dot / norms if norms else 0.0


def keyword_score(question: str, content: str) -> float:
    query = content_terms(question)
    words = content_terms(content)
    if not query:
        return 0.0
    return len(query & words) / len(query)


def has_conflicting_evidence(question: str, evidence: list[dict[str, Any]]) -> bool:
    """Conservative contradiction guard for explicit supported/unsupported claims."""
    relevant = [item["content"].casefold() for item in evidence if keyword_score(question, item["content"]) >= 0.25]
    affirmative = any(re.search(r"\b(can|supports?|available|enabled|allows?|is supported)\b", text) for text in relevant)
    negative = any(re.search(r"\b(cannot|can't|does not|doesn't|do not|don't|not supported|not support|unavailable|disabled|no longer)\b", text) for text in relevant)
    return affirmative and negative


async def retrieve(
    question: str,
    store: KnowledgeStore,
    embedder: Embedder,
    *,
    limit: int = 6,
    customer_id: str | None = None,
) -> list[dict[str, Any]]:
    vector = await embedder.embed(question)
    if len(vector) != store.embedding_dimensions:
        raise ValueError("Embedding dimension does not match the configured vector store")
    candidates = store.search_chunks(vector, limit)
    for approved in store.search_approved_knowledge(vector, customer_id):
        source = next((item for item in approved["evidence"] if item.get("url") and store.source_is_active(item["url"])), None)
        if source is None:
            continue
        candidates.append({
            "chunk_id": f"approved:{approved['id']}",
            "article_id": "",
            "section_heading": "Human-approved knowledge",
            "content": approved["answer"],
            "embedding": approved["embedding"],
            "metadata": {"image_urls": [], "approved_knowledge": True, "version": approved["version"]},
            "url": source["url"],
            "title": f"Human-reviewed: {source.get('title', 'Knowledge article')}",
        })
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        vector_score = candidate.get("vector_score")
        if vector_score is None:
            vector_score = cosine_similarity(vector, candidate["embedding"])
        lexical_score = keyword_score(question, candidate["content"])
        candidate["vector_score"] = vector_score
        candidate["keyword_score"] = lexical_score
        candidate["score"] = max(0.0, min(1.0, 0.78 * max(0.0, vector_score) + 0.22 * lexical_score))
        scored.append(candidate)
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]
