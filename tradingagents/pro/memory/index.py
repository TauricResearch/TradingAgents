"""Vector index interface + the dependency-free default implementation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from tradingagents.pro.memory.records import MemoryKind, MemoryRecord


@dataclass(frozen=True)
class SearchHit:
    record: MemoryRecord
    score: float  # cosine similarity, -1..1


class VectorIndex(Protocol):
    def add(self, record: MemoryRecord, vector: list[float]) -> None: ...

    def search(
        self,
        vector: list[float],
        k: int = 5,
        kinds: tuple[MemoryKind, ...] | None = None,
        symbol: str | None = None,
    ) -> list[SearchHit]: ...


def cosine(a: list[float], b: list[float]) -> float:
    dot = math.fsum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(math.fsum(x * x for x in a))
    nb = math.sqrt(math.fsum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorIndex:
    """Exact cosine search over an in-process list.

    Scoring is one numpy matmul over pre-normalized unit vectors — the
    backtest pipeline calls search 4× per decision against a growing
    index, and the previous per-pair ``math.fsum`` cosine dominated whole
    runs (profiled: 55% of a full backtest). Results are identical
    (same scores to float precision, same stable tie ordering); filters
    still see every record. Fine for the memory sizes this project will
    see for a long time (thousands of records); the Qdrant adapter
    exists for beyond that (ADR-0020).
    """

    def __init__(self):
        self._items: list[tuple[MemoryRecord, list[float]]] = []
        self._units: list[np.ndarray] = []
        self._matrix: np.ndarray | None = None  # rebuilt lazily after adds

    def __len__(self) -> int:
        return len(self._items)

    def add(self, record: MemoryRecord, vector: list[float]) -> None:
        if self._units and len(vector) != self._units[0].shape[0]:
            raise ValueError(
                f"vector dimension {len(vector)} != index dimension "
                f"{self._units[0].shape[0]}"
            )
        arr = np.asarray(vector, dtype=np.float64)
        norm = float(np.linalg.norm(arr))
        self._units.append(arr / norm if norm else np.zeros_like(arr))
        self._items.append((record, vector))
        self._matrix = None

    def search(
        self,
        vector: list[float],
        k: int = 5,
        kinds: tuple[MemoryKind, ...] | None = None,
        symbol: str | None = None,
    ) -> list[SearchHit]:
        if not self._items:
            return []
        if len(vector) != self._units[0].shape[0]:
            raise ValueError(
                f"query dimension {len(vector)} != index dimension "
                f"{self._units[0].shape[0]}"
            )
        if self._matrix is None:
            self._matrix = np.vstack(self._units)
        query = np.asarray(vector, dtype=np.float64)
        norm = float(np.linalg.norm(query))
        query = query / norm if norm else np.zeros_like(query)
        scores = self._matrix @ query
        hits = []
        for i, (record, _) in enumerate(self._items):
            if kinds is not None and record.kind not in kinds:
                continue
            if symbol is not None and record.symbol != symbol:
                continue
            hits.append(SearchHit(record=record, score=float(scores[i])))
        hits.sort(key=lambda h: h.score, reverse=True)  # stable: ties keep insertion order
        return hits[:k]
