from __future__ import annotations

from datetime import date, timedelta

_A_SHARE_SUFFIXES = {"SH", "SS", "SZ"}

# Mainland exchanges close on weekends plus the annual State Council public-holiday windows.
# Weekend make-up workdays do not become exchange trading days.
_A_SHARE_HOLIDAYS = {
    date(2024, 1, 1),
    *[date(2024, 2, day) for day in range(10, 18)],
    *[date(2024, 4, day) for day in range(4, 7)],
    *[date(2024, 5, day) for day in range(1, 6)],
    *[date(2024, 6, day) for day in range(8, 11)],
    *[date(2024, 9, day) for day in range(15, 18)],
    *[date(2024, 10, day) for day in range(1, 8)],
    date(2025, 1, 1),
    *[date(2025, 1, day) for day in range(28, 32)],
    *[date(2025, 2, day) for day in range(1, 5)],
    *[date(2025, 4, day) for day in range(4, 7)],
    *[date(2025, 5, day) for day in range(1, 6)],
    *[date(2025, 5, day) for day in range(31, 32)],
    *[date(2025, 6, day) for day in range(1, 3)],
    *[date(2025, 10, day) for day in range(1, 9)],
    *[date(2026, 1, day) for day in range(1, 4)],
    *[date(2026, 2, day) for day in range(15, 24)],
    *[date(2026, 4, day) for day in range(4, 7)],
    *[date(2026, 5, day) for day in range(1, 6)],
    *[date(2026, 6, day) for day in range(19, 22)],
    *[date(2026, 9, day) for day in range(25, 28)],
    *[date(2026, 10, day) for day in range(1, 8)],
}


def is_non_trading_day(ticker: str, day: date) -> bool:
    """Return whether the requested date is a known non-trading day for the ticker's market."""
    if day.weekday() >= 5:
        return True
    if _is_a_share_ticker(ticker):
        return day in _A_SHARE_HOLIDAYS
    return _is_nyse_holiday(day)


def _is_a_share_ticker(ticker: str) -> bool:
    suffix = ticker.rsplit(".", 1)[-1].upper() if "." in ticker else ""
    return suffix in _A_SHARE_SUFFIXES


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

    # When Jan 1 falls on Saturday, NYSE observes New Year's Day on the prior Friday.
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
