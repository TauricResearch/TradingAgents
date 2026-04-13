from datetime import date

from orchestrator.market_calendar import is_non_trading_day


def test_is_non_trading_day_marks_a_share_holiday():
    assert is_non_trading_day('600519.SS', date(2024, 10, 2)) is True


def test_is_non_trading_day_marks_nyse_holiday():
    assert is_non_trading_day('AAPL', date(2024, 3, 29)) is True


def test_is_non_trading_day_leaves_regular_weekday_open():
    assert is_non_trading_day('AAPL', date(2024, 3, 28)) is False
