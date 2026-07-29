"""Non-secret durable run and artifact metadata."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal

from tradingagents.observability.events import EVENT_SCHEMA_VERSION

RUN_ID_PATTERN = re.compile(r"^run_\d{8}T\d{12}Z_[0-9a-f]{8}$")
RUN_STATUSES = frozenset(
    {
        "created",
        "running",
        "cancel_requested",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
    }
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def generate_run_id(captured_at: datetime | None = None) -> str:
    captured = (captured_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return f"run_{captured.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid.uuid4().hex[:8]}"


def validate_run_id(run_id: str) -> None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("invalid run_id")


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    status: str
    ticker: str
    asset_type: Literal["stock", "crypto"]
    analysis_date: str
    selected_analysts: tuple[str, ...]
    max_debate_rounds: int
    max_risk_discuss_rounds: int
    output_language: str
    llm_provider: str
    quick_think_llm: str
    deep_think_llm: str
    configured_keys: dict[str, bool]
    created_at: str
    updated_at: str
    latest_sequence: int = 0
    final_signal: str | None = None
    # Explicit canonical report locator for new completed runs.  Older runs
    # deserialize with None and are handled by the frontend's unique-locator
    # compatibility fallback.
    final_report_artifact_id: str | None = None
    # Timestamp of the terminal run.completed event, not the report file mtime.
    completed_at: str | None = None
    # Kept structurally present for new snapshots.  P2 fills normalized source
    # degradation entries; P0 intentionally emits the empty tuple.
    degraded_data_sources: tuple[dict[str, Any], ...] = ()
    summary: str | None = None
    error_category: str | None = None
    error_message: str | None = None
    error_traceback: str | None = None
    retry_of: str | None = None
    resumed_from_sequence: int | None = None
    resume_fingerprint: dict[str, Any] | None = None
    runtime_semantics_hash: str | None = None
    agent_state_schema_sha256: str | None = None
    artifacts: tuple[str, ...] = ()
    redaction_manifest: tuple[str, ...] = ()
    event_schema_version: int = EVENT_SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_run_id(self.run_id)
        if self.status not in RUN_STATUSES:
            raise ValueError(f"invalid run status: {self.status}")
        if not self.ticker.strip():
            raise ValueError("ticker is required")
        if self.latest_sequence < 0:
            raise ValueError("latest_sequence must be non-negative")
        if self.max_debate_rounds < 1 or self.max_risk_discuss_rounds < 1:
            raise ValueError("debate and risk rounds must be positive")
        if self.event_schema_version != EVENT_SCHEMA_VERSION:
            raise ValueError("unsupported event schema version")

    @classmethod
    def create(
        cls,
        *,
        ticker: str,
        analysis_date: str,
        asset_type: Literal["stock", "crypto"] = "stock",
        selected_analysts: tuple[str, ...] = ("market", "social", "news", "fundamentals"),
        max_debate_rounds: int = 1,
        max_risk_discuss_rounds: int = 1,
        output_language: str = "English",
        llm_provider: str = "",
        quick_think_llm: str = "",
        deep_think_llm: str = "",
        configured_keys: dict[str, bool] | None = None,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> RunSnapshot:
        captured = utc_timestamp()
        return cls(
            run_id=run_id or generate_run_id(),
            status="created",
            ticker=ticker,
            asset_type=asset_type,
            analysis_date=analysis_date,
            selected_analysts=selected_analysts,
            max_debate_rounds=max_debate_rounds,
            max_risk_discuss_rounds=max_risk_discuss_rounds,
            output_language=output_language,
            llm_provider=llm_provider,
            quick_think_llm=quick_think_llm,
            deep_think_llm=deep_think_llm,
            configured_keys=configured_keys or {},
            created_at=captured,
            updated_at=captured,
            **kwargs,
        )

    def evolve(self, **changes: Any) -> RunSnapshot:
        return replace(self, **changes)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RunSnapshot:
        copied = dict(value)
        for field_name in (
            "selected_analysts",
            "artifacts",
            "redaction_manifest",
            "degraded_data_sources",
        ):
            copied[field_name] = tuple(copied.get(field_name, ()))
        return cls(**copied)


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    status: str
    ticker: str
    analysis_date: str
    asset_type: str
    created_at: str
    updated_at: str
    latest_sequence: int
    final_signal: str | None = None
    summary: str | None = None

    @classmethod
    def from_snapshot(cls, snapshot: RunSnapshot) -> RunSummary:
        return cls(
            run_id=snapshot.run_id,
            status=snapshot.status,
            ticker=snapshot.ticker,
            analysis_date=snapshot.analysis_date,
            asset_type=snapshot.asset_type,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
            latest_sequence=snapshot.latest_sequence,
            final_signal=snapshot.final_signal,
            summary=snapshot.summary,
        )
