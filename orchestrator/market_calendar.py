from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

_A_SHARE_SUFFIXES = {"SH", "SS", "SZ"}
_DEFAULT_MARKET_HOLIDAYS_PATH = Path(__file__).with_name("data") / "market_holidays.json"


def is_non_trading_day(ticker: str, day: date, *, data_path: Path | None = None) -> bool:
    """Return whether the requested date is a known non-trading day for the ticker's market."""
    if day.weekday() >= 5:
        return True
    market = market_for_ticker(ticker)
    if market == "a_share":
        return day in get_market_holidays(market, day.year, data_path=data_path)
    if market == "nyse":
        return _is_nyse_holiday(day)
    return False


def market_for_ticker(ticker: str) -> str:
    suffix = ticker.rsplit(".", 1)[-1].upper() if "." in ticker else ""
    if suffix in _A_SHARE_SUFFIXES:
        return "a_share"
    return "nyse"


def get_market_holidays(market: str, year: int, *, data_path: Path | None = None) -> set[date]:
    holidays_by_market = load_market_holidays(data_path=data_path)
    market_data = holidays_by_market.get(market, {})
    values = market_data.get(str(year), [])
    return {date.fromisoformat(raw) for raw in values}


def load_market_holidays(*, data_path: Path | None = None) -> dict[str, dict[str, list[str]]]:
    path = _resolve_market_holidays_path(data_path)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    return {
        str(market): {str(year): list(days) for year, days in years.items()}
        for market, years in payload.items()
    }


def update_market_holidays(
    *,
    market: str,
    year: int,
    holiday_dates: list[date | str],
    data_path: Path | None = None,
) -> Path:
    path = _resolve_market_holidays_path(data_path)
    payload = load_market_holidays(data_path=path)
    payload.setdefault(market, {})
    normalized_days = sorted(
        {
            item.isoformat() if isinstance(item, date) else date.fromisoformat(item).isoformat()
            for item in holiday_dates
        }
    )
    payload[market][str(year)] = normalized_days
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return path


def _resolve_market_holidays_path(data_path: Path | None = None) -> Path:
    if data_path is not None:
        return data_path
    env_path = os.environ.get("TRADINGAGENTS_MARKET_HOLIDAYS_PATH")
    if env_path:
        return Path(env_path)
    return _DEFAULT_MARKET_HOLIDAYS_PATH


def _is_nyse_holiday(day: date) -> bool:
    observed_new_year = _observed_fixed_holiday(day.year, 1, 1)
    observed_juneteenth = _observed_fixed_holiday(day.year, 6, 19)
    observed_independence_day = _observed_fixed_holiday(day.year, 7, 4)
    observed_christmas = _observed_fixed_holiday(day.year, 12, 25)

    holidays = {
        observed_new_year,
        _nth_weekday(day.year, 1, 0, 3),   # Martin Luther King, Jr. Day
        _nth_weekday(day.year, 2, 0, 3),   # Washington's Birthday
        _easter(day.year) - timedelta(days=2),  # Good Friday
        _last_weekday(day.year, 5, 0),     # Memorial Day
        observed_independence_day,
        _nth_weekday(day.year, 9, 0, 1),   # Labor Day
        _nth_weekday(day.year, 11, 3, 4),  # Thanksgiving Day
        observed_christmas,
    }
    if day.year >= 2022:
        holidays.add(observed_juneteenth)

    if day.month == 12 and day.day == 31:
        next_new_year = _observed_fixed_holiday(day.year + 1, 1, 1)
        if next_new_year.year == day.year:
            holidays.add(next_new_year)

    return day in holidays


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    delta = (weekday - first.weekday()) % 7
    return first + timedelta(days=delta + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        cursor = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        cursor = date(year, month + 1, 1) - timedelta(days=1)
    while cursor.weekday() != weekday:
        cursor -= timedelta(days=1)
    return cursor


def _easter(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)
