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


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    # HashEmbedder outputs are already unit-normalized, so dot product suffices.
    return sum(x * y for x, y in zip(a, b))


@lru_cache(maxsize=1)
def get_embedder() -> EmbeddingProvider:
    settings = get_settings()
    return HashEmbedder(dims=settings.memory_embedding_dims)


__all__ = ["EmbeddingProvider", "HashEmbedder", "cosine", "get_embedder", "_tokens"]
