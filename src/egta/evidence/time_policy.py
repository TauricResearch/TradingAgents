"""Point-in-time admissibility for evidence items (INV-02).
All comparisons happen in UTC.
No time-of-day inference, no local timezone, no daylight-saving handling.
Anything undeterminable is excluded with a recorded reason.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

_DATE_ONLY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class TimeVerdict:
    admissible: bool
    availability: str
    reason_code: str | None
    normalized_at: str | None


# Each code is mapped to ReasonCode by the service layer once contracts v1 is published.
REASON_EVIDENCE_MISSING = "EVIDENCE_MISSING"
REASON_FUTURE_DATA = "FUTURE_DATA"
REASON_INVALID_TIME = "INVALID_TIME"
AVAILABLE = "available"
UNAVAILABLE = "unavailable"


def _normalize_as_of(as_of) -> datetime:
    if isinstance(as_of, str):
        try:
            parsed = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("as_of must be timezone-aware") from exc
        if parsed.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
    elif isinstance(as_of, datetime):
        parsed = as_of
        if parsed.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
    else:
        raise ValueError("as_of must be timezone-aware")
    return parsed.astimezone(UTC)


def _excluded(reason_code: str) -> TimeVerdict:
    return TimeVerdict(
        admissible=False,
        availability=UNAVAILABLE,
        reason_code=reason_code,
        normalized_at=None,
    )


def _admitted(normalized_at: str | None) -> TimeVerdict:
    return TimeVerdict(
        admissible=True,
        availability=AVAILABLE,
        reason_code=None,
        normalized_at=normalized_at,
    )


def _parse_instant(value) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _decide_date(published_at, as_of: datetime) -> TimeVerdict:
    if not isinstance(published_at, str):
        return _excluded(REASON_INVALID_TIME)
    if _DATE_ONLY_RE.fullmatch(published_at) is None:
        return _excluded(REASON_INVALID_TIME)
    try:
        published_date = date.fromisoformat(published_at)
    except ValueError:
        return _excluded(REASON_INVALID_TIME)
    as_of_date = as_of.astimezone(UTC).date()
    if published_date < as_of_date:
        return _admitted(_date_floor(published_date))
    # Same-date equality is deliberately FUTURE_DATA, not INVALID_TIME: the value
    # parses, but the day's full data cannot exist at as_of.
    return _excluded(REASON_FUTURE_DATA)


def _date_floor(published_date: date) -> str:
    return datetime(
        published_date.year, published_date.month, published_date.day, tzinfo=UTC
    ).isoformat()


def _decide_instant(published_at, as_of: datetime) -> TimeVerdict:
    parsed = _parse_instant(published_at)
    if parsed is None:
        return _excluded(REASON_INVALID_TIME)
    if parsed.tzinfo is None:
        return _excluded(REASON_INVALID_TIME)
    normalized = parsed.astimezone(UTC)
    if normalized > as_of:
        return _excluded(REASON_FUTURE_DATA)
    return _admitted(normalized.isoformat())


def is_admissible(*, published_at, time_granularity: str, as_of) -> TimeVerdict:
    as_of_utc = _normalize_as_of(as_of)

    if published_at is None or published_at == "":
        return _excluded(REASON_EVIDENCE_MISSING)

    if time_granularity == "none":
        return _decide_instant(published_at, as_of_utc)

    if time_granularity in ("date_only", "day"):
        return _decide_date(published_at, as_of_utc)

    return _decide_instant(published_at, as_of_utc)
