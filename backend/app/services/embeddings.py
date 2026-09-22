"""Portable embedder (Phase 11).

The `HashEmbedder` produces normalized bag-of-tokens vectors using stable
`hashlib.blake2b` digests as bucket indices. Because it's deterministic and
zero-dependency it doubles as a reliable fallback whenever a real embedding
provider is unavailable — the platform still gets semantically-meaningful
retrieval (any two texts sharing tokens will have positive cosine similarity)
without ever hitting the network.
"""
from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import List
import logging

import httpx

from app.core.config import get_settings

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "of", "to", "in", "on", "is", "am", "are", "was", "were",
        "be", "been", "being", "for", "and", "or", "but", "if", "then", "so", "as",
        "at", "by", "with", "from", "that", "this", "these", "those", "it", "its",
        "i", "you", "he", "she", "we", "they", "me", "my", "your", "our", "their",
        "him", "her", "them", "his", "hers", "ours", "theirs", "yours", "myself",
        "do", "does", "did", "have", "has", "had", "will", "would", "should", "can",
        "could", "may", "might", "must", "not", "no", "yes",
    }
)


def _tokens(text: str) -> List[str]:
    return [
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if t and t.lower() not in _STOPWORDS and len(t) > 1
    ]


class EmbeddingProvider(ABC):
    name: str = "abstract"
    dims: int = 0

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:  # pragma: no cover
        ...


class HashEmbedder(EmbeddingProvider):
    name = "hash-v1"

    def __init__(self, dims: int = 256) -> None:
        self.dims = int(dims)

    def _hash_bucket(self, token: str) -> int:
        h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(h, "big") % self.dims

    def embed(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for text in texts:
            vec = [0.0] * self.dims
            for tok in _tokens(text):
                vec[self._hash_bucket(tok)] += 1.0
                # Character bigrams add a bit of "fuzz" for near-matches.
                if len(tok) >= 4:
                    for i in range(len(tok) - 1):
                        vec[self._hash_bucket(tok[i : i + 2])] += 0.5
            norm = math.sqrt(sum(v * v for v in vec))
            out.append([v / norm for v in vec] if norm else vec)
        return out


class OpenAICompatibleEmbedder(EmbeddingProvider):
    """Remote semantic embeddings with a privacy-preserving local fallback."""

    def __init__(self, *, base_url: str, api_key: str, model: str, fallback: HashEmbedder) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = model
        self.fallback = fallback
        self.dims = 0

    def embed(self, texts: List[str]) -> List[List[float]]:
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "input": texts},
                )
                response.raise_for_status()
                rows = sorted(response.json()["data"], key=lambda item: item["index"])
                vectors = [[float(value) for value in item["embedding"]] for item in rows]
                if len(vectors) != len(texts) or any(not vector for vector in vectors):
                    raise ValueError("embedding provider returned an invalid batch")
                self.dims = len(vectors[0])
                return vectors
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "semantic embeddings unavailable; using local fallback (%s)", type(exc).__name__
            )
            return self.fallback.embed(texts)


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    # HashEmbedder outputs are already unit-normalized, so dot product suffices.
    return sum(x * y for x, y in zip(a, b))


@lru_cache(maxsize=1)
def get_embedder() -> EmbeddingProvider:
    settings = get_settings()
    fallback = HashEmbedder(dims=settings.memory_embedding_dims)
    if settings.embedding_api_base and settings.embedding_api_key:
        return OpenAICompatibleEmbedder(
            base_url=settings.embedding_api_base,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            fallback=fallback,
        )
    return fallback


__all__ = ["EmbeddingProvider", "HashEmbedder", "OpenAICompatibleEmbedder", "cosine", "get_embedder", "_tokens"]
