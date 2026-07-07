"""Session-awareness boundaries (UTC, documented in ADR-0012)."""

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.contracts import TradingSession
from tradingagents.pro.ingestion.sessions import current_session

# 2026-07-01 is a Wednesday
WED = datetime(2026, 7, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (0, TradingSession.ASIA),
        (6, TradingSession.ASIA),
        (7, TradingSession.LONDON),
        (11, TradingSession.LONDON),
        (12, TradingSession.NEW_YORK),
        (20, TradingSession.NEW_YORK),
        (21, TradingSession.CLOSED),  # daily settlement break
        (22, TradingSession.ASIA),
        (23, TradingSession.ASIA),
    ],
)
def test_weekday_session_boundaries(hour, expected):
    assert current_session(WED.replace(hour=hour)) is expected


def test_weekend_is_closed():
    friday_late = datetime(2026, 7, 3, 21, 30, tzinfo=timezone.utc)
    saturday = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
    sunday_before_open = datetime(2026, 7, 5, 21, 0, tzinfo=timezone.utc)
    sunday_after_open = datetime(2026, 7, 5, 22, 30, tzinfo=timezone.utc)

    assert current_session(friday_late) is TradingSession.CLOSED
    assert current_session(saturday) is TradingSession.CLOSED
    assert current_session(sunday_before_open) is TradingSession.CLOSED
    assert current_session(sunday_after_open) is TradingSession.ASIA


def test_non_utc_timezone_is_normalized():
    # 17:30 IST == 12:00 UTC -> New York session
    ist = timezone(timedelta(hours=5, minutes=30))
    assert current_session(datetime(2026, 7, 1, 17, 30, tzinfo=ist)) is TradingSession.NEW_YORK


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        current_session(datetime(2026, 7, 1, 12, 0))
