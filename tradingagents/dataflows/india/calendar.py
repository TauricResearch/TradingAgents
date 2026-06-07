"""India market calendar helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml


INDIA_TZ = ZoneInfo("Asia/Kolkata")


class IndiaCalendarError(ValueError):
    """Raised for invalid India market dates."""


def _parse_date(value: str | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError as exc:
        raise IndiaCalendarError("Use analysis dates in YYYY-MM-DD format.") from exc


def load_holidays(path: str | Path = "config/india_market_holidays.yml") -> set[date]:
    holiday_path = Path(path)
    if not holiday_path.exists():
        return set()
    raw = yaml.safe_load(holiday_path.read_text(encoding="utf-8")) or {}
    values = raw.get("holidays", raw if isinstance(raw, list) else [])
    return {_parse_date(item) for item in values}


def is_india_trading_day(value: str | date, holidays: set[date] | None = None) -> bool:
    current = _parse_date(value)
    if current.weekday() >= 5:
        return False
    return current not in (holidays or set())


def previous_india_trading_day(
    value: str | date,
    holidays: set[date] | None = None,
) -> date:
    current = _parse_date(value) - timedelta(days=1)
    holiday_set = holidays or set()
    while not is_india_trading_day(current, holiday_set):
        current -= timedelta(days=1)
    return current


def resolve_india_analysis_date(
    value: str | date,
    *,
    roll_back_non_trading_day: bool = True,
    holidays_path: str | Path = "config/india_market_holidays.yml",
    today: date | None = None,
) -> tuple[str, list[str]]:
    """Validate an India analysis date and optionally roll back weekends/holidays."""
    requested = _parse_date(value)
    current_today = today or datetime.now(INDIA_TZ).date()
    if requested > current_today:
        raise IndiaCalendarError("Analysis date cannot be in the future.")

    holidays = load_holidays(holidays_path)
    warnings: list[str] = []
    resolved = requested
    if not is_india_trading_day(requested, holidays):
        if not roll_back_non_trading_day:
            raise IndiaCalendarError("Selected date is not an India trading day.")
        resolved = previous_india_trading_day(requested, holidays)
        warnings.append(
            f"{requested.isoformat()} is not an India trading day; using {resolved.isoformat()}."
        )
    return resolved.isoformat(), warnings


def get_last_completed_india_trading_day(
    *,
    today: date | None = None,
    holidays_path: str | Path = "config/india_market_holidays.yml",
) -> str:
    current_today = today or datetime.now(INDIA_TZ).date()
    holidays = load_holidays(holidays_path)
    if is_india_trading_day(current_today, holidays):
        return current_today.isoformat()
    return previous_india_trading_day(current_today, holidays).isoformat()
