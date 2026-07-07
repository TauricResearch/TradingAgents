"""Optional Qdrant-backed index (ADR-0020). Requires the ``qdrant`` extra:

    pip install "tradingagents[qdrant]"

Supports Qdrant's embedded local mode (``path=...``) and remote servers
(``url=...``); the interface matches InMemoryVectorIndex so ProMemory is
backend-agnostic.
"""

from __future__ import annotations

from tradingagents.pro.memory.index import SearchHit
from tradingagents.pro.memory.records import MemoryKind, MemoryRecord


class QdrantIndex:
    def __init__(
        self,
        dim: int,
        collection: str = "tradingagents_pro_memory",
        url: str | None = None,
        path: str | None = None,
    ):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:  # pragma: no cover - exercised only without extra
            raise ImportError(
                "qdrant-client is not installed; pip install 'tradingagents[qdrant]'"
            ) from exc

        if url:
            self._client = QdrantClient(url=url)
        elif path:
            self._client = QdrantClient(path=path)
        else:
            self._client = QdrantClient(":memory:")
        self._collection = collection
        if not self._client.collection_exists(collection):
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def add(self, record: MemoryRecord, vector: list[float]) -> None:
        from qdrant_client.models import PointStruct

        self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=record.id,
                    vector=vector,
                    payload={"record": record.model_dump(mode="json")},
                )
            ],
        )

    def search(
        self,
        vector: list[float],
        k: int = 5,
        kinds: tuple[MemoryKind, ...] | None = None,
        symbol: str | None = None,
    ) -> list[SearchHit]:
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        conditions = []
        if kinds is not None:
            conditions.append(
                FieldCondition(
                    key="record.kind", match=MatchAny(any=[k.value for k in kinds])
                )
            )
        if symbol is not None:
            conditions.append(
                FieldCondition(key="record.symbol", match=MatchValue(value=symbol))
            )
        response = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=k,
            query_filter=Filter(must=conditions) if conditions else None,
        )
        return [
            SearchHit(
                record=MemoryRecord.model_validate(point.payload["record"]),
                score=point.score,
            )
            for point in response.points
        ]
