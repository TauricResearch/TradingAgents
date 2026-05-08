import pytest
from typing import Optional


@pytest.mark.unit
class TestIsWin:
    def test_long_up(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(+1, 0.05) is True

    def test_long_down(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(+1, -0.03) is False

    def test_short_down(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(-1, -0.04) is True

    def test_short_up(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(-1, 0.02) is False

    def test_hold_excluded(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(0, 0.05) is None

    def test_tie_excluded(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(+1, 0.0) is None


@pytest.mark.unit
class TestGetHoldingDays:
    def test_override_takes_precedence(self):
        from tradingagents.backtesting.report import get_holding_days
        assert get_holding_days("2024-01-01", "2024-02-01", hold_days_override=5) == 5

    def test_next_signal_date_used(self):
        from tradingagents.backtesting.report import get_holding_days
        # 2024-01-01 (Mon) to 2024-01-08 (Mon) = 5 business days
        days = get_holding_days("2024-01-01", "2024-01-08", hold_days_override=None)
        assert days == 5

    def test_fallback_for_last_date(self):
        from tradingagents.backtesting.report import get_holding_days
        days = get_holding_days("2024-12-01", None, hold_days_override=None)
        assert days == 21

    def test_minimum_one_day(self):
        from tradingagents.backtesting.report import get_holding_days
        # Same date — should not return 0 or negative
        days = get_holding_days("2024-01-01", "2024-01-01", hold_days_override=None)
        assert days >= 1


@pytest.mark.unit
class TestBusinessDaysBetween:
    def test_monday_to_monday(self):
        from tradingagents.backtesting.report import business_days_between
        # 2024-01-01 (Mon) to 2024-01-08 (Mon) = 5 business days
        assert business_days_between("2024-01-01", "2024-01-08") == 5

    def test_same_date_is_zero(self):
        from tradingagents.backtesting.report import business_days_between
        assert business_days_between("2024-01-01", "2024-01-01") == 0
