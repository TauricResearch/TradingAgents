import uuid
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tradingagents_service.precedents import (
    build_embedding,
    build_precedent_document,
    build_precedent_query_text,
    cosine_similarity,
    precedent_document_to_dict,
    stable_hash,
)

from .models import (
    EvaluationDataset,
    EvaluationDatasetItem,
    EvaluationQueueAssignment,
    EvaluationRubric,
    EvaluationRun,
    EvaluationRunStatus,
    EvaluationScore,
    HumanAnnotation,
    ShadowMemoryEntry,
    ShadowRun,
    ShadowRunArtifact,
    ShadowRunEvent,
    ShadowRunOutput,
    ShadowRunPrecedent,
    ShadowRunStatus,
)


@dataclass(frozen=True)
class ArtifactCreate:
    artifact_type: str
    path: str
    metadata_json: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class PrecedentMatch:
    run_id: uuid.UUID
    ticker: str
    trade_date: date
    similarity: float
    content_text: str
    content_hash: str
    embedding_model: str
    metadata_json: dict[str, Any] | None
    created_at: datetime | None = None


@dataclass(frozen=True)
class RankedPrecedent:
    precedent: Any
    similarity: float

    @property
    def run_id(self) -> Any:
        return getattr(self.precedent, "run_id", getattr(self.precedent, "id", None))

    @property
    def ticker(self) -> Any:
        return getattr(self.precedent, "ticker", None)

    @property
    def trade_date(self) -> Any:
        return getattr(self.precedent, "trade_date", None)

    @property
    def content_text(self) -> Any:
        return getattr(self.precedent, "content_text", getattr(self.precedent, "source_text", ""))

    @property
    def content_hash(self) -> Any:
        return getattr(self.precedent, "content_hash", None)

    @property
    def embedding_model(self) -> Any:
        return getattr(self.precedent, "embedding_model", "hashed-bow-v1")

    @property
    def metadata_json(self) -> Any:
        return getattr(self.precedent, "metadata_json", None)


@dataclass(frozen=True)
class PrecedentCreate:
    run_id: uuid.UUID
    ticker: str
    trade_date: date
    source_text: str
    selected_analysts: list[str] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    embedding: list[float] | None = None
    content_hash: str | None = None
    metadata_json: dict[str, Any] | None = None
    embedding_model: str = "hashed-bow-v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(
            self,
            "selected_analysts",
            ShadowRunRepository.normalize_selected_analysts(self.selected_analysts),
        )
        if self.content_hash is None:
            object.__setattr__(self, "content_hash", ShadowRunRepository.build_content_hash(self.source_text))
        if self.embedding is None:
            object.__setattr__(
                self,
                "embedding",
                ShadowRunRepository.build_precedent_embedding(self.source_text),
            )
        else:
            object.__setattr__(self, "embedding", ShadowRunRepository.normalize_embedding(self.embedding))


@dataclass(frozen=True)
class EvaluationScoreCreate:
    dimension: str
    score: float
    confidence: float
    pass_fail: bool
    basis: str = "heuristic"
    rationale: str | None = None
    evidence_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class AnnotationCreate:
    label: str
    severity: str
    notes: str
    basis: str = "derived"
    annotator_actor_type: str = "system"
    annotator_actor_id: str = "evaluation-queue"
    annotator_role: str = "evaluator"
    evidence_json: dict[str, Any] | None = None


class ShadowRunRepository:
    PRECEDENT_EMBEDDING_DIMENSIONS = 64

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_queued_run(
        self,
        *,
        ticker: str,
        trade_date: date,
        selected_analysts: list[str],
        idempotency_key: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        metadata_json: Optional[dict[str, Any]] = None,
    ) -> ShadowRun:
        stmt = (
            insert(ShadowRun)
            .values(
                ticker=ticker,
                trade_date=trade_date,
                selected_analysts=selected_analysts,
                idempotency_key=idempotency_key,
                provider=provider,
                model=model,
                metadata_json=metadata_json,
                status=ShadowRunStatus.QUEUED,
            )
            .on_conflict_do_nothing(index_elements=[ShadowRun.idempotency_key])
            .returning(ShadowRun.id)
        )
        run_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if run_id is None:
            existing_stmt = select(ShadowRun.id).where(ShadowRun.idempotency_key == idempotency_key)
            run_id = (await self.session.execute(existing_stmt)).scalar_one()
        await self.session.commit()
        return await self.get_run_by_id(run_id)

    @staticmethod
    def build_idempotency_key(
        *,
        ticker: str,
        trade_date: date,
        selected_analysts: list[str],
        provider: str | None,
        model: str | None,
    ) -> str:
        payload = {
            "ticker": ticker,
            "trade_date": trade_date.isoformat(),
            "selected_analysts": sorted(selected_analysts),
            "provider": provider or "",
            "model": model or "",
        }
        serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def build_content_hash(source_text: str) -> str:
        return stable_hash(source_text)

    @staticmethod
    def normalize_selected_analysts(selected_analysts: Iterable[str] | None) -> list[str]:
        if selected_analysts is None:
            return []
        return sorted({analyst.strip().lower() for analyst in selected_analysts if analyst and analyst.strip()})

    @staticmethod
    def normalize_embedding(embedding: Iterable[float]) -> list[float]:
        return [float(value) for value in embedding]

    @staticmethod
    def build_precedent_embedding(source_text: str) -> list[float]:
        return build_embedding(source_text, dimensions=ShadowRunRepository.PRECEDENT_EMBEDDING_DIMENSIONS)

    @staticmethod
    def calculate_vector_similarity(
        query_embedding: Iterable[float],
        candidate_embedding: Iterable[float],
        *,
        metric: str = "cosine",
    ) -> float:
        query = ShadowRunRepository.normalize_embedding(query_embedding)
        candidate = ShadowRunRepository.normalize_embedding(candidate_embedding)
        if metric == "cosine":
            return cosine_similarity(query, candidate)
        if metric in {"dot", "dot_product"}:
            if len(query) != len(candidate) or not query:
                return 0.0
            return float(sum(left * right for left, right in zip(query, candidate)))
        raise ValueError(f"Unsupported precedent similarity metric: {metric}")

    @staticmethod
    def rank_precedents_by_similarity(
        precedents: Iterable[Any],
        *,
        query_embedding: Iterable[float],
        metric: str = "cosine",
        limit: int = 10,
    ) -> list[RankedPrecedent]:
        matches: list[RankedPrecedent] = []
        for precedent in precedents:
            embedding_payload = getattr(precedent, "embedding_json", None)
            if isinstance(embedding_payload, dict):
                candidate_embedding = embedding_payload.get("vector")
            else:
                candidate_embedding = getattr(precedent, "embedding", None)
            if not isinstance(candidate_embedding, list):
                continue
            score = ShadowRunRepository.calculate_vector_similarity(
                query_embedding,
                candidate_embedding,
                metric=metric,
            )
            matches.append(
                RankedPrecedent(
                    precedent=precedent,
                    similarity=round(score, 6),
                )
            )
        matches.sort(
            key=lambda item: (
                item.similarity,
                getattr(item.precedent, "trade_date", date.min),
            ),
            reverse=True,
        )
        return matches[:limit]

    async def get_run_by_id(self, run_id: uuid.UUID) -> Optional[ShadowRun]:
        stmt: Select[tuple[ShadowRun]] = select(ShadowRun).where(ShadowRun.id == run_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_run_by_idempotency_key(self, idempotency_key: str) -> Optional[ShadowRun]:
        stmt: Select[tuple[ShadowRun]] = select(ShadowRun).where(ShadowRun.idempotency_key == idempotency_key)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_runs(
        self,
        *,
        status: Optional[ShadowRunStatus] = None,
        ticker: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ShadowRun]:
        stmt = select(ShadowRun)
        if status is not None:
            stmt = stmt.where(ShadowRun.status == status)
        if ticker is not None:
            stmt = stmt.where(ShadowRun.ticker == ticker)
        if date_from is not None:
            stmt = stmt.where(ShadowRun.trade_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(ShadowRun.trade_date <= date_to)
        stmt = stmt.order_by(ShadowRun.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_events_by_run_id(self, run_id: uuid.UUID) -> list[ShadowRunEvent]:
        stmt = select(ShadowRunEvent).where(ShadowRunEvent.run_id == run_id).order_by(ShadowRunEvent.sequence.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_artifacts_by_run_id(self, run_id: uuid.UUID) -> list[ShadowRunArtifact]:
        stmt = select(ShadowRunArtifact).where(ShadowRunArtifact.run_id == run_id).order_by(ShadowRunArtifact.created_at.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_output_by_run_id(self, run_id: uuid.UUID) -> Optional[ShadowRunOutput]:
        stmt = select(ShadowRunOutput).where(ShadowRunOutput.run_id == run_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_precedent_embedding(
        self,
        *,
        run_id: uuid.UUID,
        ticker: str,
        trade_date: date,
        content_text: str,
        provider: str | None = None,
        model: str | None = None,
        selected_analysts: Iterable[str] | None = None,
        embedding: Iterable[float] | None = None,
        content_hash: str | None = None,
        metadata_json: Optional[dict[str, Any]] = None,
        embedding_model: str = "hashed-bow-v1",
    ) -> ShadowRunPrecedent:
        document = build_precedent_document(
            run_id=str(run_id),
            ticker=ticker.strip().upper(),
            trade_date=trade_date.isoformat(),
            content_text=content_text,
            metadata=metadata_json or {},
            embedding_model=embedding_model,
        )
        normalized_embedding = self.normalize_embedding(embedding) if embedding is not None else document.embedding
        normalized_selected_analysts = self.normalize_selected_analysts(selected_analysts)
        normalized_content_hash = content_hash or document.content_hash
        stmt = (
            insert(ShadowRunPrecedent)
            .values(
                run_id=run_id,
                ticker=document.ticker,
                trade_date=trade_date,
                provider=provider,
                model=model,
                selected_analysts=normalized_selected_analysts,
                embedding_model=document.embedding_model,
                content_text=document.content_text,
                content_hash=normalized_content_hash,
                embedding_json={"vector": normalized_embedding},
                metadata_json=document.metadata,
            )
            .on_conflict_do_update(
                index_elements=[ShadowRunPrecedent.run_id],
                set_={
                    "ticker": document.ticker,
                    "trade_date": trade_date,
                    "provider": provider,
                    "model": model,
                    "selected_analysts": normalized_selected_analysts,
                    "embedding_model": document.embedding_model,
                    "content_text": document.content_text,
                    "content_hash": normalized_content_hash,
                    "embedding_json": {"vector": normalized_embedding},
                    "metadata_json": document.metadata,
                    "updated_at": func.now(),
                },
            )
            .returning(ShadowRunPrecedent.id)
        )
        precedent_id = (await self.session.execute(stmt)).scalar_one()
        await self.session.commit()
        return await self._get_precedent_by_id(precedent_id)

    async def upsert_run_precedent(self, precedent: PrecedentCreate) -> ShadowRunPrecedent:
        return await self.upsert_precedent_embedding(
            run_id=precedent.run_id,
            ticker=precedent.ticker,
            trade_date=precedent.trade_date,
            content_text=precedent.source_text,
            provider=precedent.provider,
            model=precedent.model,
            selected_analysts=precedent.selected_analysts,
            embedding=precedent.embedding,
            content_hash=precedent.content_hash,
            metadata_json=precedent.metadata_json,
            embedding_model=precedent.embedding_model,
        )

    async def _get_precedent_by_id(self, precedent_id: uuid.UUID) -> ShadowRunPrecedent:
        stmt = select(ShadowRunPrecedent).where(ShadowRunPrecedent.id == precedent_id)
        return (await self.session.execute(stmt)).scalar_one()

    async def get_precedent_by_run_id(self, run_id: uuid.UUID) -> Optional[ShadowRunPrecedent]:
        stmt = select(ShadowRunPrecedent).where(ShadowRunPrecedent.run_id == run_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def search_precedents(
        self,
        *,
        ticker: str | None = None,
        before_trade_date: date | None = None,
        trade_date: date | None = None,
        provider: str | None = None,
        model: str | None = None,
        selected_analysts: Iterable[str] | None = None,
        content_hash: str | None = None,
        query_text: str | None = None,
        query_embedding: list[float] | None = None,
        exclude_run_id: uuid.UUID | None = None,
        metric: str = "cosine",
        limit: int = 10,
        candidate_limit: int = 200,
    ) -> list[PrecedentMatch]:
        stmt = select(ShadowRunPrecedent)
        if ticker is not None:
            stmt = stmt.where(ShadowRunPrecedent.ticker == ticker.strip().upper())
        if trade_date is not None:
            stmt = stmt.where(ShadowRunPrecedent.trade_date == trade_date)
        if before_trade_date is not None:
            stmt = stmt.where(ShadowRunPrecedent.trade_date < before_trade_date)
        if provider is not None:
            stmt = stmt.where(ShadowRunPrecedent.provider == provider)
        if model is not None:
            stmt = stmt.where(ShadowRunPrecedent.model == model)
        if selected_analysts is not None:
            stmt = stmt.where(ShadowRunPrecedent.selected_analysts == self.normalize_selected_analysts(selected_analysts))
        if content_hash is not None:
            stmt = stmt.where(ShadowRunPrecedent.content_hash == content_hash)
        if exclude_run_id is not None:
            stmt = stmt.where(ShadowRunPrecedent.run_id != exclude_run_id)
        stmt = stmt.order_by(ShadowRunPrecedent.trade_date.desc(), ShadowRunPrecedent.created_at.desc()).limit(
            max(limit, candidate_limit)
        )
        candidates = list((await self.session.execute(stmt)).scalars().all())
        if not candidates:
            return []

        if query_embedding is None:
            query_embedding = build_embedding(query_text or "")

        return self.rank_precedents_by_similarity(
            candidates,
            query_embedding=query_embedding,
            metric=metric,
            limit=limit,
        )

    async def query_nearest_precedents(
        self,
        *,
        query_embedding: Iterable[float],
        ticker: str | None = None,
        trade_date: date | None = None,
        provider: str | None = None,
        model: str | None = None,
        selected_analysts: Iterable[str] | None = None,
        content_hash: str | None = None,
        exclude_run_id: uuid.UUID | None = None,
        metric: str = "cosine",
        limit: int = 10,
        candidate_limit: int = 200,
    ) -> list[PrecedentMatch]:
        return await self.search_precedents(
            ticker=ticker,
            trade_date=trade_date,
            provider=provider,
            model=model,
            selected_analysts=selected_analysts,
            content_hash=content_hash,
            query_embedding=list(query_embedding),
            exclude_run_id=exclude_run_id,
            metric=metric,
            limit=limit,
            candidate_limit=candidate_limit,
        )

    async def lookup_run_precedents(
        self,
        *,
        ticker: str,
        trade_date: date,
        query_text: str | None = None,
        query_embedding: Iterable[float] | None = None,
        provider: str | None = None,
        model: str | None = None,
        selected_analysts: Iterable[str] | None = None,
        metric: str = "cosine",
        limit: int = 10,
        candidate_limit: int = 200,
    ) -> list[PrecedentMatch]:
        if query_embedding is None and query_text is not None:
            query_embedding = self.build_precedent_embedding(query_text)
        return await self.search_precedents(
            ticker=ticker,
            before_trade_date=trade_date,
            provider=provider,
            model=model,
            selected_analysts=selected_analysts,
            query_embedding=list(query_embedding) if query_embedding is not None else None,
            query_text=query_text or "",
            metric=metric,
            limit=limit,
            candidate_limit=candidate_limit,
        )

    async def search_precedents_for_run(
        self,
        *,
        run_id: uuid.UUID,
        limit: int = 10,
    ) -> list[PrecedentMatch]:
        run = await self.get_run_by_id(run_id)
        output = await self.get_output_by_run_id(run_id)
        precedent = await self.get_precedent_by_run_id(run_id)
        if run is None:
            return []
        query_text = build_precedent_query_text(run=run, output=output, quality=(output.provider_metadata.get("quality") if output and isinstance(output.provider_metadata, dict) else {}))
        query_embedding = build_embedding(query_text)
        search_before = run.trade_date
        if precedent is not None:
            search_before = precedent.trade_date
        return await self.search_precedents(
            ticker=run.ticker,
            before_trade_date=search_before,
            query_embedding=query_embedding,
            exclude_run_id=run_id,
            limit=limit,
        )

    async def append_event(
        self,
        *,
        run_id: uuid.UUID,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> ShadowRunEvent:
        await self.session.execute(select(ShadowRun.id).where(ShadowRun.id == run_id).with_for_update())
        sequence_stmt = select(func.coalesce(func.max(ShadowRunEvent.sequence), 0) + 1).where(
            ShadowRunEvent.run_id == run_id
        )
        next_sequence = (await self.session.execute(sequence_stmt)).scalar_one()
        event = ShadowRunEvent(run_id=run_id, sequence=next_sequence, event_type=event_type, payload=payload)
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def upsert_output_summary(
        self,
        *,
        run_id: uuid.UUID,
        final_rating: Optional[str] = None,
        decision_markdown: Optional[str] = None,
        state_log_dir: Optional[str] = None,
        memory_log_path: Optional[str] = None,
        provider_metadata: Optional[dict[str, Any]] = None,
    ) -> ShadowRunOutput:
        stmt = (
            insert(ShadowRunOutput)
            .values(
                run_id=run_id,
                final_rating=final_rating,
                decision_markdown=decision_markdown,
                state_log_dir=state_log_dir,
                memory_log_path=memory_log_path,
                provider_metadata=provider_metadata,
            )
            .on_conflict_do_update(
                index_elements=[ShadowRunOutput.run_id],
                set_={
                    "final_rating": final_rating,
                    "decision_markdown": decision_markdown,
                    "state_log_dir": state_log_dir,
                    "memory_log_path": memory_log_path,
                    "provider_metadata": provider_metadata,
                    "updated_at": func.now(),
                },
            )
            .returning(ShadowRunOutput.id)
        )
        output_id = (await self.session.execute(stmt)).scalar_one()
        await self.session.commit()
        return await self._get_output_by_id(output_id)

    async def insert_artifact_records(self, *, run_id: uuid.UUID, artifacts: Iterable[ArtifactCreate]) -> list[ShadowRunArtifact]:
        rows = [
            ShadowRunArtifact(
                run_id=run_id,
                artifact_type=artifact.artifact_type,
                path=artifact.path,
                metadata_json=artifact.metadata_json,
            )
            for artifact in artifacts
        ]
        if not rows:
            return []
        self.session.add_all(rows)
        await self.session.commit()
        for row in rows:
            await self.session.refresh(row)
        return rows

    async def claim_next_queued_run(self) -> Optional[ShadowRun]:
        subquery = (
            select(ShadowRun.id)
            .where(ShadowRun.status == ShadowRunStatus.QUEUED)
            .order_by(ShadowRun.queued_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        stmt = (
            update(ShadowRun)
            .where(ShadowRun.id == subquery.scalar_subquery())
            .values(status=ShadowRunStatus.RUNNING, started_at=func.now(), updated_at=func.now())
            .returning(ShadowRun.id)
        )
        run_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if run_id is None:
            await self.session.rollback()
            return None
        await self.session.commit()
        return await self.get_run_by_id(run_id)

    async def requeue_stale_running_runs(self, *, stale_after_seconds: int) -> int:
        cutoff = datetime.now().astimezone() - timedelta(seconds=stale_after_seconds)
        stmt = (
            update(ShadowRun)
            .where(ShadowRun.status == ShadowRunStatus.RUNNING)
            .where(ShadowRun.updated_at < cutoff)
            .values(
                status=ShadowRunStatus.QUEUED,
                started_at=None,
                updated_at=func.now(),
                error_message="Requeued after stale worker heartbeat.",
            )
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return int(result.rowcount or 0)

    async def set_run_status(
        self,
        *,
        run_id: uuid.UUID,
        new_status: ShadowRunStatus,
        error_message: Optional[str] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[ShadowRun]:
        current = await self.get_run_by_id(run_id)
        if current is None:
            return None
        self._assert_status_transition(current.status, new_status)

        values: dict[str, Any] = {"status": new_status, "updated_at": func.now()}
        if new_status in (ShadowRunStatus.SUCCEEDED, ShadowRunStatus.FAILED, ShadowRunStatus.CANCELLED):
            values["completed_at"] = completed_at or func.now()
        if new_status == ShadowRunStatus.FAILED:
            values["error_message"] = error_message
        elif error_message is not None:
            values["error_message"] = error_message

        await self.session.execute(update(ShadowRun).where(ShadowRun.id == run_id).values(**values))
        await self.session.commit()
        return await self.get_run_by_id(run_id)

    async def mark_run_succeeded_atomic(
        self,
        *,
        run_id: uuid.UUID,
        final_rating: Optional[str] = None,
        decision_markdown: Optional[str] = None,
        state_log_dir: Optional[str] = None,
        memory_log_path: Optional[str] = None,
        provider_metadata: Optional[dict[str, Any]] = None,
        artifacts: Iterable[ArtifactCreate] = (),
    ) -> Optional[ShadowRun]:
        run_stmt = select(ShadowRun).where(ShadowRun.id == run_id).with_for_update()
        run = (await self.session.execute(run_stmt)).scalar_one_or_none()
        if run is None:
            await self.session.rollback()
            return None
        if run.status == ShadowRunStatus.SUCCEEDED:
            await self.session.rollback()
            return run
        self._assert_status_transition(run.status, ShadowRunStatus.SUCCEEDED)

        output_stmt = (
            insert(ShadowRunOutput)
            .values(
                run_id=run_id,
                final_rating=final_rating,
                decision_markdown=decision_markdown,
                state_log_dir=state_log_dir,
                memory_log_path=memory_log_path,
                provider_metadata=provider_metadata,
            )
            .on_conflict_do_update(
                index_elements=[ShadowRunOutput.run_id],
                set_={
                    "final_rating": final_rating,
                    "decision_markdown": decision_markdown,
                    "state_log_dir": state_log_dir,
                    "memory_log_path": memory_log_path,
                    "provider_metadata": provider_metadata,
                    "updated_at": func.now(),
                },
            )
        )
        await self.session.execute(output_stmt)

        await self.session.execute(delete(ShadowRunArtifact).where(ShadowRunArtifact.run_id == run_id))
        artifact_rows = [
            ShadowRunArtifact(
                run_id=run_id,
                artifact_type=artifact.artifact_type,
                path=artifact.path,
                metadata_json=artifact.metadata_json,
            )
            for artifact in artifacts
        ]
        if artifact_rows:
            self.session.add_all(artifact_rows)

        await self.session.execute(
            update(ShadowRun)
            .where(ShadowRun.id == run_id)
            .values(
                status=ShadowRunStatus.SUCCEEDED,
                completed_at=func.now(),
                error_message=None,
                updated_at=func.now(),
            )
        )
        await self.session.commit()
        return await self.get_run_by_id(run_id)

    async def insert_memory_entry(
        self,
        *,
        ticker: str,
        trade_date: date,
        entry_kind: str,
        content: str,
        run_id: Optional[uuid.UUID] = None,
        metadata_json: Optional[dict[str, Any]] = None,
    ) -> ShadowMemoryEntry:
        entry = ShadowMemoryEntry(
            run_id=run_id,
            ticker=ticker,
            trade_date=trade_date,
            entry_kind=entry_kind,
            content=content,
            metadata_json=metadata_json,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def ensure_evaluation_rubric(
        self,
        *,
        name: str,
        version: str,
        scope_type: str = "shadow_run",
        status: str = "active",
        description: str | None = None,
        definition_json: dict[str, Any] | None = None,
    ) -> EvaluationRubric:
        stmt = (
            insert(EvaluationRubric)
            .values(
                name=name,
                version=version,
                scope_type=scope_type,
                status=status,
                description=description,
                definition_json=definition_json or {},
            )
            .on_conflict_do_update(
                constraint="uq_evaluation_rubrics_name_version",
                set_={
                    "scope_type": scope_type,
                    "status": status,
                    "description": description,
                    "definition_json": definition_json or {},
                    "updated_at": func.now(),
                },
            )
            .returning(EvaluationRubric.id)
        )
        rubric_id = (await self.session.execute(stmt)).scalar_one()
        await self.session.commit()
        rubric = await self.get_evaluation_rubric_by_id(rubric_id)
        if rubric is None:
            raise RuntimeError("evaluation rubric upsert failed")
        return rubric

    async def get_evaluation_rubric_by_id(self, rubric_id: uuid.UUID) -> EvaluationRubric | None:
        stmt = select(EvaluationRubric).where(EvaluationRubric.id == rubric_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_evaluation_rubrics(self, *, status: str | None = None) -> list[EvaluationRubric]:
        stmt = select(EvaluationRubric)
        if status is not None:
            stmt = stmt.where(EvaluationRubric.status == status)
        stmt = stmt.order_by(EvaluationRubric.name.asc(), EvaluationRubric.version.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def create_completed_evaluation_run(
        self,
        *,
        rubric_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        shadow_run_id: uuid.UUID | None,
        evaluator_type: str,
        evaluator_model: str | None,
        input_json: dict[str, Any],
        result_json: dict[str, Any],
        scores: Iterable[EvaluationScoreCreate],
        annotation: AnnotationCreate | None = None,
        trace_id: str | None = None,
    ) -> EvaluationRun:
        run = EvaluationRun(
            evaluation_rubric_id=rubric_id,
            target_type=target_type,
            target_id=target_id,
            shadow_run_id=shadow_run_id,
            evaluator_type=evaluator_type,
            evaluator_model=evaluator_model,
            status=EvaluationRunStatus.SUCCEEDED,
            trace_id=trace_id,
            input_json=input_json,
            result_json=result_json,
            started_at=func.now(),
            finished_at=func.now(),
        )
        self.session.add(run)
        await self.session.flush()

        self.session.add_all(
            [
                EvaluationScore(
                    evaluation_run_id=run.id,
                    dimension=score.dimension,
                    score=score.score,
                    confidence=score.confidence,
                    pass_fail=score.pass_fail,
                    basis=score.basis,
                    rationale=score.rationale,
                    evidence_json=score.evidence_json,
                )
                for score in scores
            ]
        )
        if annotation is not None:
            self.session.add(
                HumanAnnotation(
                    target_type=target_type,
                    target_id=target_id,
                    shadow_run_id=shadow_run_id,
                    evaluation_run_id=run.id,
                    annotator_actor_type=annotation.annotator_actor_type,
                    annotator_actor_id=annotation.annotator_actor_id,
                    annotator_role=annotation.annotator_role,
                    label=annotation.label,
                    severity=annotation.severity,
                    basis=annotation.basis,
                    notes=annotation.notes,
                    evidence_json=annotation.evidence_json,
                )
            )
            stmt = (
                insert(EvaluationQueueAssignment)
                .values(
                    target_type=target_type,
                    target_id=target_id,
                    shadow_run_id=shadow_run_id,
                    assigned_actor_type="system",
                    assigned_actor_id="evaluation-queue",
                    assigned_by_actor_type="system",
                    assigned_by_actor_id="observability",
                )
                .on_conflict_do_update(
                    constraint="uq_evaluation_queue_assignments_target",
                    set_={
                        "shadow_run_id": shadow_run_id,
                        "assigned_actor_type": "system",
                        "assigned_actor_id": "evaluation-queue",
                        "assigned_by_actor_type": "system",
                        "assigned_by_actor_id": "observability",
                        "updated_at": func.now(),
                    },
                )
            )
            await self.session.execute(stmt)

        await self.session.commit()
        return await self.get_evaluation_run_by_id(run.id)  # type: ignore[arg-type]

    async def get_evaluation_run_by_id(self, evaluation_run_id: uuid.UUID) -> EvaluationRun | None:
        stmt = select(EvaluationRun).where(EvaluationRun.id == evaluation_run_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_evaluation_runs(
        self,
        *,
        shadow_run_id: uuid.UUID | None = None,
        status: EvaluationRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvaluationRun]:
        stmt = select(EvaluationRun)
        if shadow_run_id is not None:
            stmt = stmt.where(EvaluationRun.shadow_run_id == shadow_run_id)
        if status is not None:
            stmt = stmt.where(EvaluationRun.status == status)
        stmt = stmt.order_by(EvaluationRun.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_evaluation_scores(self, evaluation_run_id: uuid.UUID) -> list[EvaluationScore]:
        stmt = select(EvaluationScore).where(EvaluationScore.evaluation_run_id == evaluation_run_id)
        stmt = stmt.order_by(EvaluationScore.dimension.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_annotations_for_target(self, *, target_type: str, target_id: uuid.UUID) -> list[HumanAnnotation]:
        stmt = (
            select(HumanAnnotation)
            .where(HumanAnnotation.target_type == target_type, HumanAnnotation.target_id == target_id)
            .order_by(HumanAnnotation.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def ensure_evaluation_dataset(
        self,
        *,
        name: str,
        scope_type: str = "shadow_run",
        status: str = "active",
        description: str | None = None,
        selection_rule_json: dict[str, Any] | None = None,
        basis: str = "derived",
    ) -> EvaluationDataset:
        stmt = (
            insert(EvaluationDataset)
            .values(
                name=name,
                scope_type=scope_type,
                status=status,
                description=description,
                selection_rule_json=selection_rule_json or {},
                basis=basis,
            )
            .on_conflict_do_update(
                index_elements=[EvaluationDataset.name],
                set_={
                    "scope_type": scope_type,
                    "status": status,
                    "description": description,
                    "selection_rule_json": selection_rule_json or {},
                    "basis": basis,
                    "updated_at": func.now(),
                },
            )
            .returning(EvaluationDataset.id)
        )
        dataset_id = (await self.session.execute(stmt)).scalar_one()
        await self.session.commit()
        stmt = select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
        dataset = (await self.session.execute(stmt)).scalar_one_or_none()
        if dataset is None:
            raise RuntimeError("evaluation dataset upsert failed")
        return dataset

    async def add_evaluation_dataset_item(
        self,
        *,
        dataset_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        shadow_run_id: uuid.UUID | None = None,
        evaluation_run_id: uuid.UUID | None = None,
        gold_label: str | None = None,
        gold_score: float | None = None,
        basis: str = "derived",
        notes: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> EvaluationDatasetItem:
        stmt = (
            insert(EvaluationDatasetItem)
            .values(
                dataset_id=dataset_id,
                target_type=target_type,
                target_id=target_id,
                shadow_run_id=shadow_run_id,
                evaluation_run_id=evaluation_run_id,
                gold_label=gold_label,
                gold_score=gold_score,
                basis=basis,
                notes=notes,
                metadata_json=metadata_json,
            )
            .on_conflict_do_update(
                constraint="uq_evaluation_dataset_items_target",
                set_={
                    "shadow_run_id": shadow_run_id,
                    "evaluation_run_id": evaluation_run_id,
                    "gold_label": gold_label,
                    "gold_score": gold_score,
                    "basis": basis,
                    "notes": notes,
                    "metadata_json": metadata_json,
                },
            )
            .returning(EvaluationDatasetItem.id)
        )
        item_id = (await self.session.execute(stmt)).scalar_one()
        await self.session.commit()
        stmt = select(EvaluationDatasetItem).where(EvaluationDatasetItem.id == item_id)
        return (await self.session.execute(stmt)).scalar_one()

    async def _get_output_by_id(self, output_id: uuid.UUID) -> ShadowRunOutput:
        stmt = select(ShadowRunOutput).where(ShadowRunOutput.id == output_id)
        return (await self.session.execute(stmt)).scalar_one()

    @staticmethod
    def _assert_status_transition(current: ShadowRunStatus, new: ShadowRunStatus) -> None:
        allowed: dict[ShadowRunStatus, set[ShadowRunStatus]] = {
            ShadowRunStatus.QUEUED: {ShadowRunStatus.RUNNING, ShadowRunStatus.CANCELLED},
            ShadowRunStatus.RUNNING: {ShadowRunStatus.SUCCEEDED, ShadowRunStatus.FAILED, ShadowRunStatus.CANCELLED},
            ShadowRunStatus.SUCCEEDED: set(),
            ShadowRunStatus.FAILED: set(),
            ShadowRunStatus.CANCELLED: set(),
        }
        if new == current:
            return
        if new not in allowed[current]:
            raise ValueError(f"Invalid status transition: {current.value} -> {new.value}")
