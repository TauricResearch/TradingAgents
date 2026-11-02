"""Indian exchange sessions with explicit holiday-data verification status."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

_INDIA_TZ = ZoneInfo("Asia/Kolkata")
_EXCHANGES = frozenset({"NSE", "BSE"})


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(_INDIA_TZ).date()
        return value.date()
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("session date must use YYYY-MM-DD") from exc
        if parsed.isoformat() != value:
            raise ValueError("session date must use YYYY-MM-DD")
        return parsed
    raise TypeError("session date must be a date, datetime, or ISO date string")


def _metadata_date(value: date | str | None, field: str) -> date | None:
    if value is None:
        return None
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must use YYYY-MM-DD") from exc
        if parsed.isoformat() != value:
            raise ValueError(f"{field} must use YYYY-MM-DD")
        return parsed
    raise TypeError(f"{field} must be a date or YYYY-MM-DD string")


class CalendarCoverageError(ValueError):
    """The requested day falls outside the calendar dataset's declared range."""


@dataclass(frozen=True)
class IndianExchangeCalendar:
    """Weekday sessions plus caller-supplied holidays; no holiday list is bundled."""

    exchange: str
    holidays: tuple[date | str, ...] = ()
    holiday_source: str | None = None
    last_updated: date | str | None = None
    holidays_verified: bool = False
    holiday_verified_by: str | None = None
    coverage_start: date | str | None = None
    coverage_end: date | str | None = None

    def __post_init__(self):
        if not isinstance(self.exchange, str):
            raise ValueError("exchange must be NSE or BSE")
        exchange = self.exchange.strip().upper()
        if exchange not in _EXCHANGES:
            raise ValueError("exchange must be NSE or BSE")
        object.__setattr__(self, "exchange", exchange)
        object.__setattr__(self, "holidays", frozenset(_as_date(day) for day in self.holidays))
        object.__setattr__(self, "last_updated", _metadata_date(self.last_updated, "last_updated"))
        object.__setattr__(self, "coverage_start", _metadata_date(self.coverage_start, "coverage_start"))
        object.__setattr__(self, "coverage_end", _metadata_date(self.coverage_end, "coverage_end"))
        if (self.coverage_start is None) != (self.coverage_end is None):
            raise ValueError("coverage_start and coverage_end must be supplied together")
        if self.coverage_start is not None and self.coverage_start > self.coverage_end:
            raise ValueError("coverage_start must not be after coverage_end")
        if not isinstance(self.holidays_verified, bool):
            raise ValueError("holidays_verified must be a bool")
        for field in ("holiday_source", "holiday_verified_by"):
            value = getattr(self, field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field} must be a non-empty string when supplied")
            if isinstance(value, str):
                object.__setattr__(self, field, value.strip())
        if self.holidays_verified:
            required = (
                self.holiday_source,
                self.last_updated,
                self.holiday_verified_by,
                self.coverage_start,
                self.coverage_end,
            )
            if not all(required):
                raise ValueError(
                    "verified holidays require source, last_updated, verifier, and coverage bounds"
                )
            if self.last_updated > datetime.now(_INDIA_TZ).date():
                raise ValueError("verified_on cannot be in the future")
        if self.coverage_start is not None and any(
            holiday < self.coverage_start or holiday > self.coverage_end
            for holiday in self.holidays
        ):
            raise ValueError("holiday dates must fall within the declared coverage")

    @classmethod
    def from_csv(cls, exchange: str, csv_path: str | Path) -> IndianExchangeCalendar:
        """Load verified exchange holidays from a supplied CSV file.

        Required columns: ``exchange,date,source,verified_on,verified_by``,
        ``verification_status``, ``coverage_start`` and ``coverage_end``.
        Every row for the requested exchange must be explicitly marked
        ``verified`` and use consistent source and coverage metadata. A blank
        date row can carry verified metadata for a range with no holidays.
        """
        if not isinstance(exchange, str):
            raise ValueError("exchange must be NSE or BSE")
        requested = exchange.strip().upper()
        if requested not in _EXCHANGES:
            raise ValueError("exchange must be NSE or BSE")
        required = {
            "exchange", "date", "source", "verified_on", "verified_by",
            "verification_status", "coverage_start", "coverage_end",
        }
        with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError(f"holiday CSV must include: {', '.join(sorted(required))}")
            rows = [
                (line, row)
                for line, row in enumerate(reader, start=2)
                if (row.get("exchange") or "").strip().upper() == requested
            ]

        if not rows:
            raise ValueError(f"holiday CSV contains no rows for {requested}")
        metadata = set()
        holidays = []
        for line, row in rows:
            if (row.get("verification_status") or "").strip().casefold() != "verified":
                raise ValueError(f"holiday CSV row {line} is not marked verified")
            source = (row.get("source") or "").strip()
            verified_on = (row.get("verified_on") or "").strip()
            verified_by = (row.get("verified_by") or "").strip()
            coverage_start = (row.get("coverage_start") or "").strip()
            coverage_end = (row.get("coverage_end") or "").strip()
            if not source or not verified_on or not verified_by or not coverage_start or not coverage_end:
                raise ValueError(f"holiday CSV row {line} is missing verification metadata")
            try:
                verified_date = _metadata_date(verified_on, "verified_on")
                parsed_coverage_start = _metadata_date(coverage_start, "coverage_start")
                parsed_coverage_end = _metadata_date(coverage_end, "coverage_end")
                holiday_value = (row.get("date") or "").strip()
                holiday = _as_date(holiday_value) if holiday_value else None
            except ValueError as exc:
                raise ValueError(f"invalid date in holiday CSV row {line}") from exc
            metadata.add((
                source,
                verified_date,
                verified_by,
                parsed_coverage_start,
                parsed_coverage_end,
            ))
            if holiday is not None:
                holidays.append(holiday)
        if len(metadata) != 1:
            raise ValueError(f"holiday CSV metadata for {requested} must be consistent")
        source, verified_date, verified_by, coverage_start, coverage_end = metadata.pop()
        return cls(
            exchange=requested,
            holidays=tuple(holidays),
            holiday_source=source,
            last_updated=verified_date,
            holidays_verified=True,
            holiday_verified_by=verified_by,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )

    @property
    def holiday_data_status(self) -> str:
        if self.holidays_verified:
            return "verified"
        return "unverified" if self.holidays else "weekends_only_unverified"

    def _ensure_covered(self, day: date) -> None:
        if self.coverage_start is not None and not self.coverage_start <= day <= self.coverage_end:
            raise CalendarCoverageError(
                f"{day} is outside {self.exchange} calendar coverage "
                f"{self.coverage_start}..{self.coverage_end}"
            )

    def is_session(self, value: date | datetime | str) -> bool:
        day = _as_date(value)
        self._ensure_covered(day)
        return day.weekday() < 5 and day not in self.holidays

    def session_bounds(
        self, value: date | datetime | str
    ) -> tuple[datetime, datetime] | None:
        """Return local NSE/BSE regular-session bounds, or None on a non-session."""
        day = _as_date(value)
        if not self.is_session(day):
            return None
        return (
            datetime.combine(day, time(9, 15), tzinfo=_INDIA_TZ),
            datetime.combine(day, time(15, 30), tzinfo=_INDIA_TZ),
        )

    def is_open(self, value: datetime) -> bool:
        """Whether an aware timestamp (or naive India-local timestamp) is in session."""
        if not isinstance(value, datetime):
            raise TypeError("timestamp must be a datetime")
        local = value.replace(tzinfo=_INDIA_TZ) if value.tzinfo is None else value.astimezone(_INDIA_TZ)
        bounds = self.session_bounds(local.date())
        return bounds is not None and bounds[0] <= local < bounds[1]