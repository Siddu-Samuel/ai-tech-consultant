"""Embedding and database synchronization for the resumable crawl manifest."""

import hashlib
from typing import Any

from app.database import KnowledgeStore
from app.embeddings import Embedder


async def index_manifest(manifest: dict[str, Any], store: KnowledgeStore, embedder: Embedder, *, model_label: str, dimensions: int) -> dict[str, int]:
    counts = {"embedded": 0, "reused": 0, "chunks": 0}
    for page in manifest.get("pages", {}).values():
        if page.get("status") != "active":
            continue
        images_by_heading: dict[str, list[str]] = {}
        for image in page.get("images", []):
            context = " ".join(value for value in (image.get("alt_text", ""), image.get("description", "")) if value)
            if context:
                images_by_heading.setdefault(image.get("section_heading", ""), []).append(context)
        for chunk in page.get("chunks", []):
            text = chunk.get("content", "") + "\n" + "\n".join(images_by_heading.get(chunk.get("section_heading", ""), []))
            version = hashlib.sha256(f"{model_label}\0{dimensions}\0{text}".encode("utf-8")).hexdigest()
            existing = chunk.get("embedding")
            if chunk.get("embedding_hash") == version and isinstance(existing, list) and len(existing) == dimensions:
                counts["reused"] += 1
            else:
                vector = await embedder.embed(text)
                if len(vector) != dimensions:
                    raise ValueError(f"Embedding dimension mismatch: expected {dimensions}, got {len(vector)}")
                chunk["embedding"] = vector
                chunk["embedding_hash"] = version
                chunk["embedding_model"] = model_label
                counts["embedded"] += 1
            counts["chunks"] += 1
    store.sync_manifest(manifest)
    return counts
