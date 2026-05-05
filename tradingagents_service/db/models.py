import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ShadowRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ShadowRun(Base):
    __tablename__ = "shadow_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    selected_analysts: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[ShadowRunStatus] = mapped_column(
        Enum(
            ShadowRunStatus,
            name="shadow_run_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ShadowRunStatus.QUEUED,
    )
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    events = relationship("ShadowRunEvent", back_populates="run", cascade="all, delete-orphan")
    artifacts = relationship("ShadowRunArtifact", back_populates="run", cascade="all, delete-orphan")
    output = relationship("ShadowRunOutput", back_populates="run", uselist=False, cascade="all, delete-orphan")
    memory_entries = relationship("ShadowMemoryEntry", back_populates="run", cascade="all, delete-orphan")
    precedents = relationship("ShadowRunPrecedent", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_shadow_runs_status_queued_at", "status", "queued_at"),)


class ShadowRunEvent(Base):
    __tablename__ = "shadow_run_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shadow_runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run = relationship("ShadowRun", back_populates="events")
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_shadow_run_events_run_sequence"),
        Index("ix_shadow_run_events_run_id", "run_id"),
    )


class ShadowRunArtifact(Base):
    __tablename__ = "shadow_run_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shadow_runs.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run = relationship("ShadowRun", back_populates="artifacts")
    __table_args__ = (Index("ix_shadow_run_artifacts_run_id", "run_id"),)


class ShadowRunOutput(Base):
    __tablename__ = "shadow_run_outputs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shadow_runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    final_rating: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_log_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_log_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    run = relationship("ShadowRun", back_populates="output")


class ShadowRunPrecedent(Base):
    __tablename__ = "shadow_run_precedents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shadow_runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    selected_analysts: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False, default="hashed-bow-v1")
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    run = relationship("ShadowRun", back_populates="precedents")

    __table_args__ = (
        Index("ix_shadow_run_precedents_ticker_trade_date", "ticker", "trade_date"),
        Index("ix_shadow_run_precedents_provider_model", "provider", "model"),
        Index("ix_shadow_run_precedents_content_hash", "content_hash"),
        Index("ix_shadow_run_precedents_selected_analysts", "selected_analysts", postgresql_using="gin"),
    )


class ShadowMemoryEntry(Base):
    __tablename__ = "shadow_memory_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shadow_runs.id", ondelete="SET NULL"), nullable=True
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run = relationship("ShadowRun", back_populates="memory_entries")
    __table_args__ = (Index("ix_shadow_memory_entries_ticker_trade_date", "ticker", "trade_date"),)


class EvaluationRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvaluationRubric(Base):
    __tablename__ = "evaluation_rubrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False, default="shadow_run")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    evaluation_runs = relationship("EvaluationRun", back_populates="rubric")

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_evaluation_rubrics_name_version"),
        Index("ix_evaluation_rubrics_status", "status"),
        Index("ix_evaluation_rubrics_scope_type", "scope_type"),
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_rubric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_rubrics.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, default="shadow_run")
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shadow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shadow_runs.id", ondelete="CASCADE"), nullable=True
    )
    evaluator_type: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    evaluator_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[EvaluationRunStatus] = mapped_column(
        Enum(
            EvaluationRunStatus,
            name="evaluation_run_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=EvaluationRunStatus.QUEUED,
    )
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    rubric = relationship("EvaluationRubric", back_populates="evaluation_runs")
    scores = relationship("EvaluationScore", back_populates="evaluation_run", cascade="all, delete-orphan")
    annotations = relationship("HumanAnnotation", back_populates="evaluation_run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_evaluation_runs_status", "status"),
        Index("ix_evaluation_runs_target", "target_type", "target_id"),
        Index("ix_evaluation_runs_shadow_run_id", "shadow_run_id"),
        Index("ix_evaluation_runs_created_at", "created_at"),
    )


class EvaluationScore(Base):
    __tablename__ = "evaluation_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(128), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pass_fail: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    basis: Mapped[str] = mapped_column(String(32), nullable=False, default="heuristic")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    evaluation_run = relationship("EvaluationRun", back_populates="scores")

    __table_args__ = (
        UniqueConstraint("evaluation_run_id", "dimension", name="uq_evaluation_scores_run_dimension"),
        Index("ix_evaluation_scores_dimension", "dimension"),
        Index("ix_evaluation_scores_basis", "basis"),
    )


class HumanAnnotation(Base):
    __tablename__ = "human_annotations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shadow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shadow_runs.id", ondelete="CASCADE"), nullable=True
    )
    evaluation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_runs.id", ondelete="SET NULL"), nullable=True
    )
    annotator_actor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    annotator_actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    annotator_role: Mapped[str] = mapped_column(String(64), nullable=False, default="evaluator")
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    basis: Mapped[str] = mapped_column(String(32), nullable=False, default="derived")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    evaluation_run = relationship("EvaluationRun", back_populates="annotations")

    __table_args__ = (
        Index("ix_human_annotations_target", "target_type", "target_id"),
        Index("ix_human_annotations_shadow_run_id", "shadow_run_id"),
        Index("ix_human_annotations_evaluation_run_id", "evaluation_run_id"),
        Index("ix_human_annotations_label", "label"),
    )


class EvaluationDataset(Base):
    __tablename__ = "evaluation_datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False, default="shadow_run")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    selection_rule_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    basis: Mapped[str] = mapped_column(String(32), nullable=False, default="derived")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    items = relationship("EvaluationDatasetItem", back_populates="dataset", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_evaluation_datasets_status", "status"),
        Index("ix_evaluation_datasets_scope_type", "scope_type"),
    )


class EvaluationDatasetItem(Base):
    __tablename__ = "evaluation_dataset_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shadow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shadow_runs.id", ondelete="CASCADE"), nullable=True
    )
    evaluation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_runs.id", ondelete="SET NULL"), nullable=True
    )
    gold_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gold_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    basis: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    dataset = relationship("EvaluationDataset", back_populates="items")

    __table_args__ = (
        UniqueConstraint("dataset_id", "target_type", "target_id", name="uq_evaluation_dataset_items_target"),
        Index("ix_evaluation_dataset_items_dataset_id", "dataset_id"),
        Index("ix_evaluation_dataset_items_target", "target_type", "target_id"),
    )


class EvaluationQueueAssignment(Base):
    __tablename__ = "evaluation_queue_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shadow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shadow_runs.id", ondelete="CASCADE"), nullable=True
    )
    assigned_actor_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    assigned_actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    assigned_by_actor_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    assigned_by_actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("target_type", "target_id", name="uq_evaluation_queue_assignments_target"),
        Index("ix_evaluation_queue_assignments_assignee", "assigned_actor_type", "assigned_actor_id"),
        Index("ix_evaluation_queue_assignments_shadow_run_id", "shadow_run_id"),
    )
