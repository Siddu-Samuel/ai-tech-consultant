"""Configurable embeddings with a clearly test-only local implementation."""

import asyncio
import hashlib
import math
import re
from typing import Protocol

import httpx


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...


def embed_local_test(text: str, dimensions: int = 64) -> list[float]:
    """Stable signed-token hashing for tests/demo only; not semantic production search."""
    vector = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        position = int.from_bytes(digest[:8], "big") % dimensions
        vector[position] += 1.0 if digest[8] % 2 else -1.0
    norm = math.sqrt(sum(component * component for component in vector))
    return [component / norm for component in vector] if norm else vector


class LocalTestEmbedder:
    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        return embed_local_test(text, self.dimensions)


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, dimensions: int, base_url: str, timeout_seconds: float = 20.0):
        if not api_key or not model:
            raise RuntimeError("OPENAI_API_KEY and EMBEDDING_MODEL are required for the openai embedding provider")
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.endpoint = f"{base_url.rstrip('/')}/embeddings"
        self.timeout_seconds = timeout_seconds

    async def embed(self, text: str) -> list[float]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        self.endpoint,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={"model": self.model, "input": text, "dimensions": self.dimensions},
                    )
                response.raise_for_status()
                payload = response.json()
                vector = payload["data"][0]["embedding"]
                if len(vector) != self.dimensions or not all(math.isfinite(float(x)) for x in vector):
                    raise ValueError(f"Embedding provider returned an invalid vector; expected {self.dimensions} dimensions")
                return [float(value) for value in vector]
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.25 * (2**attempt))
        raise RuntimeError("Embedding request failed after bounded retries") from last_error


def create_embedder(settings: object) -> Embedder:
    provider = getattr(settings, "embedding_provider").lower()
    dimensions = getattr(settings, "embedding_dimensions")
    if provider == "local-test":
        if getattr(settings, "app_env").lower() == "production":
            raise RuntimeError("The local-test embedding adapter is not available in production")
        return LocalTestEmbedder(dimensions)
    if provider == "openai":
        return OpenAIEmbedder(
            getattr(settings, "openai_api_key"),
            getattr(settings, "embedding_model"),
            dimensions,
            getattr(settings, "openai_base_url"),
        )
    raise ValueError(f"Unsupported embedding provider: {provider}")
