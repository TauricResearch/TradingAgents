from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


DEFAULT_FIXED_CLOSURE_DATES: dict[str, str] = {
    "01-01": "New Year's Day",
    "05-01": "Labor Day / May Day",
    "06-19": "Juneteenth",
    "07-04": "Independence Day",
    "10-01": "China National Day",
    "12-25": "Christmas Day",
}


def _date_key(value: pd.Timestamp) -> str:
    return f"{value.month:02d}-{value.day:02d}"


def is_allowed_market_closure(
    value: str | pd.Timestamp,
    *,
    fixed_closures: Mapping[str, str] | None = None,
) -> bool:
    day = pd.Timestamp(value)
    if day.weekday() >= 5:
        return True
    closures = fixed_closures or DEFAULT_FIXED_CLOSURE_DATES
    return _date_key(day) in closures


def expected_trading_sessions(
    start_date: str,
    end_date: str,
    *,
    fixed_closures: Mapping[str, str] | None = None,
) -> list[str]:
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if end < start:
        raise ValueError(f"end_date {end_date} must be on or after start_date {start_date}")

    sessions: list[str] = []
    for day in pd.date_range(start, end, freq="D"):
        if is_allowed_market_closure(day, fixed_closures=fixed_closures):
            continue
        sessions.append(day.strftime("%Y-%m-%d"))
    return sessions
