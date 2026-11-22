"""RunEvent contract (implements the approved FR-05 spec).

# Implements: FR-05, NFR-08, NFR-09

The event model is immutable (``frozen`` + ``validate_assignment``), strict about
types, and JSON-safe in ``metrics`` (rejects NaN/±inf, non-dict, bytes, Decimal,
and any non-serializable object at construction). ``schema_version`` and
``duration_ms`` (NFR-09) are first-class; ``sequence`` is a strict non-negative
int; ``OK`` carries no ``reason_code`` and ``BLOCKED`` must carry one.

Definitions: docs/req/contracts-summary.md §4/§5.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_HASH_PATTERN = r"^[0-9a-f]{64}$"


class Phase(StrEnum):
    """Pipeline phase that produced an event."""

    EVIDENCE = "evidence"
    BUDGET = "budget"
    DELIBERATION = "deliberation"
    RISK_GATE = "risk_gate"
    LEDGER = "ledger"
    EVALUATION = "evaluation"
    APP = "app"


class RunStatus(StrEnum):
    """Phase status; BLOCKED/INCOMPLETE/REVIEW/FAILED are system states."""

    STARTED = "started"
    OK = "ok"
    BLOCKED = "blocked"
    INCOMPLETE = "incomplete"
    REVIEW = "review"
    FAILED = "failed"


class ReasonCode(StrEnum):
    """Canonical, shared refusal/failure reason codes."""

    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    FUTURE_DATA = "FUTURE_DATA"
    BUDGET_DENIED = "BUDGET_DENIED"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    POLICY_REJECTED = "POLICY_REJECTED"
    STALE_PORTFOLIO = "STALE_PORTFOLIO"
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"
    INCOMPATIBLE_STATE = "INCOMPATIBLE_STATE"
    INVALID_TIME = "INVALID_TIME"
    STALE_DATA = "STALE_DATA"
    VENDOR_UNAVAILABLE = "VENDOR_UNAVAILABLE"
    INVALID_CITATION = "INVALID_CITATION"
    INTEGRITY_VIOLATION = "INTEGRITY_VIOLATION"


def _reject_non_json(value: Any) -> None:
    """Raise ValueError if ``value`` is not a JSON-safe scalar/container."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metrics must not contain NaN/Inf")
    elif isinstance(value, bool | int | str) or value is None:
        return
    elif isinstance(value, dict):
        for k, v in value.items():
            _reject_non_json(k)
            _reject_non_json(v)
    elif isinstance(value, list | tuple):
        for v in value:
            _reject_non_json(v)
    else:
        raise ValueError(f"metrics value is not JSON-serializable: {type(value)!r}")


class RunEvent(BaseModel):
    """One append-only, immutable audit event for a run."""

    model_config = ConfigDict(
        allow_inf_nan=False, extra="forbid", frozen=True, validate_assignment=True
    )

    schema_version: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    sequence: int = Field(ge=0, strict=True)
    phase: Phase
    timestamp: datetime
    duration_ms: int = Field(ge=0, strict=True, default=0)
    status: RunStatus
    payload_hash: str = Field(pattern=_HASH_PATTERN)
    prev_event_hash: str = Field(pattern=r"^([0-9a-f]{64})?$")
    metrics: dict[str, Any] = Field(default_factory=dict)
    reason_code: ReasonCode | None = None

    @field_validator("timestamp")
    @classmethod
    def _require_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")
        return value.astimezone(UTC)

    @field_validator("metrics")
    @classmethod
    def _json_safe_metrics(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("metrics must be a dict")
        _reject_non_json(value)
        json.dumps(value)
        return value

    @model_validator(mode="after")
    def _status_reason_consistency(self) -> RunEvent:
        if self.status is RunStatus.OK and self.reason_code is not None:
            raise ValueError("OK must not carry a reason_code")
        if self.status is RunStatus.BLOCKED and self.reason_code is None:
            raise ValueError("BLOCKED must carry a reason_code")
        return self
