"""A single safe, versioned record for one analysis cycle."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tradingagents.web.run_models import RunSnapshot

CYCLE_RECORD_SCHEMA_VERSION = 1


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class CycleQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str
    asset_type: Literal["stock", "crypto"]
    analysis_date: str

    @field_validator("ticker", "analysis_date")
    @classmethod
    def _require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value is required")
        return value


class CycleSpecSnapshot(BaseModel):
    """Non-secret execution parameters needed to reproduce a cycle's scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_analysts: tuple[str, ...]
    max_debate_rounds: int = Field(ge=1)
    max_risk_discuss_rounds: int = Field(ge=1)
    output_language: str
    llm_provider: str
    quick_think_llm: str
    deep_think_llm: str
    runtime_semantics_hash: str | None = None
    effective_config_artifact_id: str | None = None


class CycleRecord(BaseModel):
    """Replay/audit boundary that intentionally excludes model-private text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[CYCLE_RECORD_SCHEMA_VERSION] = CYCLE_RECORD_SCHEMA_VERSION
    cycle_id: str = Field(default_factory=lambda: f"cycle_{uuid.uuid4().hex}")
    run_id: str
    captured_at: str = Field(default_factory=_timestamp)
    status: str
    query: CycleQuery
    spec_snapshot: CycleSpecSnapshot
    event_sequence_start: int = Field(ge=0)
    event_sequence_end: int = Field(ge=0)
    final_signal: str | None = None
    report_artifact_ids: tuple[str, ...] = ()
    scratchpad_entry_ids: tuple[str, ...] = ()
    public_context_fact_count: int = Field(default=0, ge=0)

    @field_validator("run_id", "status")
    @classmethod
    def _require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value is required")
        return value

    @classmethod
    def from_run_snapshot(
        cls,
        snapshot: RunSnapshot,
        *,
        event_sequence_start: int = 0,
        event_sequence_end: int | None = None,
        report_artifact_ids: tuple[str, ...] | list[str] = (),
        scratchpad_entry_ids: tuple[str, ...] | list[str] = (),
        public_context_fact_count: int = 0,
    ) -> CycleRecord:
        metadata = snapshot.metadata
        config_artifact = metadata.get("effective_config_artifact_id")
        return cls(
            run_id=snapshot.run_id,
            status=snapshot.status,
            query=CycleQuery(
                ticker=snapshot.ticker,
                asset_type=snapshot.asset_type,
                analysis_date=snapshot.analysis_date,
            ),
            spec_snapshot=CycleSpecSnapshot(
                selected_analysts=snapshot.selected_analysts,
                max_debate_rounds=snapshot.max_debate_rounds,
                max_risk_discuss_rounds=snapshot.max_risk_discuss_rounds,
                output_language=snapshot.output_language,
                llm_provider=snapshot.llm_provider,
                quick_think_llm=snapshot.quick_think_llm,
                deep_think_llm=snapshot.deep_think_llm,
                runtime_semantics_hash=snapshot.runtime_semantics_hash,
                effective_config_artifact_id=(
                    str(config_artifact) if config_artifact is not None else None
                ),
            ),
            event_sequence_start=event_sequence_start,
            event_sequence_end=(
                snapshot.latest_sequence
                if event_sequence_end is None
                else event_sequence_end
            ),
            final_signal=snapshot.final_signal,
            report_artifact_ids=tuple(dict.fromkeys(report_artifact_ids)),
            scratchpad_entry_ids=tuple(dict.fromkeys(scratchpad_entry_ids)),
            public_context_fact_count=public_context_fact_count,
        )
