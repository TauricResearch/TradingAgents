"""Embedding interface with a deterministic, dependency-free default.

The hashing embedder is not a semantic model — it is a signed
bag-of-words projection. It makes retrieval deterministic and offline
(tests, backtests, degraded ops); production deployments plug a real
embedding callable (OpenAI, local model) into ProMemory without touching
any other code.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol


class EmbeddingFn(Protocol):
    def __call__(self, text: str) -> list[float]: ...


_TOKEN = re.compile(r"[a-z0-9_]+")


class HashingEmbedder:
    """Signed feature-hashing embedder: deterministic, normalized, no deps."""

    def __init__(self, dim: int = 256):
        if dim < 16:
            raise ValueError("dim must be >= 16")
        self.dim = dim

    def __call__(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = _TOKEN.findall(text.lower())
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha1(token.encode()).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(math.fsum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]
