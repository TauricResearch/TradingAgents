from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnalystName(str, Enum):
    market = "market"
    social = "social"
    news = "news"
    fundamentals = "fundamentals"


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class CreateShadowRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, description="Exact instrument symbol; suffix preserved.")
    trade_date: date = Field(description="Trade date in YYYY-MM-DD.")
    selected_analysts: list[AnalystName] = Field(min_length=1)
    provider: str | None = None
    model: str | None = None
    target_profile: dict[str, Any] | None = None

    @field_validator("ticker")
    @classmethod
    def validate_ticker_non_empty(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("ticker must be non-empty")
        # Keep symbol as provided to preserve suffix and casing expectations.
        return value

    @field_validator("selected_analysts")
    @classmethod
    def validate_analysts_unique(cls, value: list[AnalystName]) -> list[AnalystName]:
        if len(set(value)) != len(value):
            raise ValueError("selected_analysts must not contain duplicates")
        return value


class RunLinks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    self: str
    events: str
    artifacts: str
    decision: str


class CreateShadowRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    status: RunStatus
    reused_existing: bool = False
    submission_kind: str = "queued"
    links: RunLinks


class ShadowRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    ticker: str
    trade_date: date
    selected_analysts: list[str]
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    provider: str | None = None
    model_name: str | None = None
    error_message: str | None = None
    target_profile: dict[str, Any] | None = None


class ShadowRunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: list[ShadowRunResponse]


class EventItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    timestamp: datetime
    event_type: str
    payload: dict[str, Any] | None = None
    sequence: int


class EventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    events: list[EventItem]


class ArtifactItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: UUID
    kind: str
    uri: str
    sha256: str
    content_type: str
    bytes: int


class ArtifactsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    artifacts: list[ArtifactItem]


class DecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    final_rating: str | None = None
    final_decision_markdown: str | None = None
    recommendation_status: str | None = None
    invalidated_by_quality_gate: bool = False
    original_final_rating: str | None = None
    invalidating_findings: list[dict[str, Any]] = Field(default_factory=list)
    state_log_dir: str | None = None
    memory_log_path: str | None = None
    provider: str | None = None
    deep_model: str | None = None
    quick_model: str | None = None
    quality_status: str | None = None
    quality_findings: list[dict[str, Any]] = Field(default_factory=list)
    source_summary: dict[str, Any] | None = None
    recommendation_audit: dict[str, Any] | None = None
    telemetry_summary: dict[str, Any] | None = None
    target_profile: dict[str, Any] | None = None
    precedent_summary: dict[str, Any] | None = None


class TraceNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    label: str
    kind: str
    status: str
    summary: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class TraceEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_node: str
    to_node: str
    label: str


class TraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    nodes: list[TraceNode]
    edges: list[TraceEdge]
    artifact_refs: list[dict[str, Any]] = Field(default_factory=list)
    precedent_summary: dict[str, Any] | None = None


class ShadowRunHandoffResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    ticker: str
    trade_date: date
    selected_analysts: list[str]
    status: RunStatus
    final_rating: str | None = None
    final_decision_markdown: str | None = None
    recommendation_status: str | None = None
    invalidated_by_quality_gate: bool = False
    original_final_rating: str | None = None
    invalidating_findings: list[dict[str, Any]] = Field(default_factory=list)
    state_log_dir: str | None = None
    memory_log_path: str | None = None
    provider: str | None = None
    model_name: str | None = None
    deep_model: str | None = None
    quick_model: str | None = None
    provider_metadata: dict[str, Any] | None = None
    quality_status: str | None = None
    quality_findings: list[dict[str, Any]] = Field(default_factory=list)
    source_summary: dict[str, Any] | None = None
    recommendation_audit: dict[str, Any] | None = None
    telemetry_summary: dict[str, Any] | None = None
    target_profile: dict[str, Any] | None = None
    precedent_summary: dict[str, Any] | None = None


class PrecedentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    ticker: str
    trade_date: date
    similarity: float
    content_hash: str
    content_text: str
    embedding_model: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime | None = None


class PrecedentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_run_id: UUID | None = None
    query_ticker: str | None = None
    query_trade_date: date | None = None
    query_text: str | None = None
    precedents: list[PrecedentItem] = Field(default_factory=list)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ok"


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ready"
