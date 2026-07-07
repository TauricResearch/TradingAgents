"""Vector index interface + the dependency-free default implementation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

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

    Fine for the memory sizes this project will see for a long time
    (thousands of records); the Qdrant adapter exists for beyond that
    (ADR-0020).
    """

    def __init__(self):
        self._items: list[tuple[MemoryRecord, list[float]]] = []

    def __len__(self) -> int:
        return len(self._items)

    def add(self, record: MemoryRecord, vector: list[float]) -> None:
        self._items.append((record, vector))

    def search(
        self,
        vector: list[float],
        k: int = 5,
        kinds: tuple[MemoryKind, ...] | None = None,
        symbol: str | None = None,
    ) -> list[SearchHit]:
        hits = []
        for record, stored in self._items:
            if kinds is not None and record.kind not in kinds:
                continue
            if symbol is not None and record.symbol != symbol:
                continue
            hits.append(SearchHit(record=record, score=cosine(vector, stored)))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]
