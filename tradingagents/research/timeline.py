"""Frozen exchange-session timing for the global-event experiment."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache


def decision_cutoff(decision_date: date) -> datetime:
    """Return midnight UTC immediately after a decision session."""
    if isinstance(decision_date, datetime) or not isinstance(decision_date, date):
        raise TypeError("decision date must be a date")
    return datetime.combine(decision_date + timedelta(days=1), time.min, timezone.utc)


@lru_cache(maxsize=1)
def _xnys_calendar():
    try:
        import exchange_calendars as xcals
    except ImportError as exc:  # pragma: no cover - clean-install smoke covers this path
        raise RuntimeError(
            "research timelines require exchange-calendars; install tradingagents[poller]"
        ) from exc
    return xcals.get_calendar("XNYS")


def require_contiguous_xnys_sessions(values: Iterable[date]) -> tuple[date, ...]:
    """Validate a non-empty, ordered, gap-free XNYS decision timeline."""
    dates = tuple(values)
    if not dates:
        raise ValueError("research timeline requires at least one decision date")
    if any(isinstance(value, datetime) or not isinstance(value, date) for value in dates):
        raise TypeError("decision dates must be date values")
    if dates != tuple(sorted(dates)) or len(set(dates)) != len(dates):
        raise ValueError("decision dates must be sorted and unique")

    calendar = _xnys_calendar()
    invalid = [value for value in dates if not calendar.is_session(value.isoformat())]
    if invalid:
        raise ValueError(
            "decision dates must be XNYS sessions: "
            + ",".join(value.isoformat() for value in invalid)
        )
    for previous, current in zip(dates, dates[1:], strict=False):
        expected = calendar.next_session(previous.isoformat()).date()
        if current != expected:
            raise ValueError("decision dates must be contiguous XNYS sessions")
    return dates


def outcome_sessions(decision_date: date) -> tuple[date, date]:
    """Return the exact next-open and following-open XNYS sessions."""
    require_contiguous_xnys_sessions((decision_date,))
    calendar = _xnys_calendar()
    entry = calendar.next_session(decision_date.isoformat())
    exit_ = calendar.next_session(entry)
    return entry.date(), exit_.date()


def outcome_capture_not_before(decision_date: date, *, delay_minutes: int) -> datetime:
    """Return the first permitted capture time after the exit-session open."""
    if isinstance(delay_minutes, bool) or not isinstance(delay_minutes, int) \
            or delay_minutes < 0:
        raise ValueError("outcome capture delay must be a non-negative integer")
    _, exit_date = outcome_sessions(decision_date)
    opened = _xnys_calendar().session_open(exit_date.isoformat()).to_pydatetime()
    return opened.astimezone(timezone.utc) + timedelta(minutes=delay_minutes)
