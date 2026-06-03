import pandas as pd

from tradingagents.dataflows.market_calendar import (
    DEFAULT_FIXED_CLOSURE_DATES,
    expected_trading_sessions,
    is_allowed_market_closure,
)


def test_expected_sessions_skip_weekends():
    assert expected_trading_sessions("2026-06-05", "2026-06-08") == [
        "2026-06-05",
        "2026-06-08",
    ]


def test_expected_sessions_skip_fixed_holiday_whitelist():
    assert expected_trading_sessions("2026-12-24", "2026-12-26") == [
        "2026-12-24",
    ]


def test_fixed_holiday_whitelist_is_deliberately_simple():
    assert DEFAULT_FIXED_CLOSURE_DATES["01-01"] == "New Year's Day"
    assert DEFAULT_FIXED_CLOSURE_DATES["07-04"] == "Independence Day"
    assert DEFAULT_FIXED_CLOSURE_DATES["12-25"] == "Christmas Day"
    assert is_allowed_market_closure(pd.Timestamp("2026-07-04")) is True
    assert is_allowed_market_closure(pd.Timestamp("2026-07-03")) is False
