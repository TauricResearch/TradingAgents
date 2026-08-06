"""Explicit point-in-time and interval semantics."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, field_validator, model_validator

from tradingagents.domain.contracts import ContractModel


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


class VintagePolicy(str, Enum):
    """Policy used to decide whether a data vintage was available."""

    OBSERVED_STRICTLY_BEFORE_CUTOFF = "observed-strictly-before-cutoff"


class AsOf(ContractModel):
    """The complete information boundary for one decision.

    Availability is deliberately strict: an observation timestamp equal to the
    cutoff is not admissible.  This removes ambiguity for events committed at
    the boundary itself.
    """

    decision_cutoff: AwareDatetime
    calendar: str
    timezone_name: str = "UTC"
    entry_session: date | None = None
    vintage_policy: VintagePolicy = VintagePolicy.OBSERVED_STRICTLY_BEFORE_CUTOFF

    @field_validator("decision_cutoff")
    @classmethod
    def normalize_cutoff(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @field_validator("calendar")
    @classmethod
    def normalize_calendar(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("calendar must not be empty")
        return value

    @field_validator("timezone_name")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        value = value.strip()
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone {value!r}") from exc
        return value

    def admits_observed_at(self, observed_at: datetime) -> bool:
        """Return whether an aware observation was available for this decision."""
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return observed_at.astimezone(timezone.utc) < self.decision_cutoff


class TimeRange(ContractModel):
    """A half-open UTC interval: ``[start, end)``."""

    start: AwareDatetime
    end: AwareDatetime

    @field_validator("start", "end")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @model_validator(mode="after")
    def validate_order(self) -> TimeRange:
        if self.start >= self.end:
            raise ValueError("time range must satisfy start < end")
        return self

    def contains(self, timestamp: datetime) -> bool:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        timestamp = timestamp.astimezone(timezone.utc)
        return self.start <= timestamp < self.end
