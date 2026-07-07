"""Typed memory records.

The memory system is append-only: closing a trade appends an outcome
record referencing the original; lessons (mistake / winning pattern) are
derived records appended at close time. Nothing is rewritten, so the JSONL
store doubles as an audit trail.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from tradingagents.contracts import utc_now


class MemoryKind(str, Enum):
    TRADE = "trade"
    OUTCOME = "outcome"
    REGIME = "regime"
    REFLECTION = "reflection"
    STRATEGY = "strategy"
    MISTAKE = "mistake"
    WINNING_PATTERN = "winning_pattern"


class MemoryRecord(BaseModel):
    """One memory: searchable text plus a structured payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: MemoryKind
    text: str = Field(min_length=1, description="What gets embedded and searched.")
    symbol: str | None = None
    payload: dict = Field(default_factory=dict)
    ref_id: str | None = Field(
        default=None, description="Id of the record this one annotates (e.g. outcome->trade)."
    )
    created_at: datetime = Field(default_factory=utc_now)
