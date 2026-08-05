"""Trading-hours gate: extended-session windowing and gap handling.

The fallback path (no exchange_calendars) is tested deterministically by forcing
``_cal = None``. A second test exercises the real NYSE calendar when the library
is installed (the ``poller`` extra), and is skipped otherwise.
"""
from datetime import datetime, timezone

import pytest

from tradingagents.dataflows.trading_clock import TradingClock


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


@pytest.fixture
def fallback_clock():
    c = TradingClock()
    c._cal = None  # force the weekends-only / fixed-hours fallback
    return c


@pytest.mark.unit
def test_fallback_polls_during_extended_weekday_hours(fallback_clock):
    # 2026-06-29 is a Monday. In EDT (UTC-4), 04:00–20:00 ET == 08:00–24:00 UTC.
    assert fallback_clock.is_polling_time(_utc(2026, 6, 29, 13, 0)) is True   # 09:00 ET
    assert fallback_clock.is_polling_time(_utc(2026, 6, 29, 8, 0)) is True    # 04:00 ET edge
    assert fallback_clock.is_polling_time(_utc(2026, 6, 29, 6, 0)) is False   # 02:00 ET, pre-session


@pytest.mark.unit
def test_fallback_skips_weekends(fallback_clock):
    # 2026-06-27 is a Saturday.
    assert fallback_clock.is_polling_time(_utc(2026, 6, 27, 16, 0)) is False


@pytest.mark.unit
def test_fallback_next_open_jumps_over_the_weekend(fallback_clock):
    # From Saturday, the next session start is Monday 04:00 ET = 08:00 UTC (EDT).
    nxt = fallback_clock.next_open(_utc(2026, 6, 27, 16, 0))
    assert nxt == _utc(2026, 6, 29, 8, 0)


@pytest.mark.unit
def test_calendar_path_respects_holidays_if_installed():
    pytest.importorskip("exchange_calendars")
    clock = TradingClock()
    if clock._cal is None:
        pytest.skip("exchange_calendars import failed at runtime")
    # 2026-01-01 (New Year's Day) is a market holiday — never a polling time.
    assert clock.is_polling_time(_utc(2026, 1, 1, 17, 0)) is False
    # A normal winter trading day (EST, UTC-5): 2026-01-05 Monday, 15:00 UTC = 10:00 ET.
    assert clock.is_polling_time(_utc(2026, 1, 5, 15, 0)) is True
