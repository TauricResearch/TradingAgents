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


from tradingagents.backtesting.models import BacktestResult


def _make_results():
    return [
        BacktestResult(ticker="NVDA", trade_date="2024-01-01", rating="Buy", direction=1),
        BacktestResult(ticker="NVDA", trade_date="2024-02-01", rating="Sell", direction=-1),
        BacktestResult(ticker="NVDA", trade_date="2024-03-01", rating="Hold", direction=0),
    ]


def _return_map(ticker, trade_date, holding_days):
    data = {
        ("NVDA", "2024-01-01"): (0.05, 0.02, 21),   # Buy → +5% → win
        ("NVDA", "2024-02-01"): (-0.03, -0.01, 21),  # Sell dir=-1, ret=-3% → win
        ("NVDA", "2024-03-01"): (0.01, 0.00, 21),    # Hold → excluded from win rate
    }
    return data.get((ticker, trade_date), (None, None, None))


@pytest.mark.unit
class TestBacktestReport:
    def test_win_rate_excludes_hold(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        with patch("tradingagents.backtesting.report.fetch_returns", side_effect=_return_map):
            summary = BacktestReport(_make_results()).compute(hold_days_override=21)

        assert summary.win_rate == pytest.approx(1.0)  # both decisive signals correct
        assert summary.hold_count == 1

    def test_signal_counts(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        with patch("tradingagents.backtesting.report.fetch_returns", side_effect=_return_map):
            summary = BacktestReport(_make_results()).compute(hold_days_override=21)

        assert summary.signal_counts == {"Buy": 1, "Sell": 1, "Hold": 1}

    def test_no_resolvable_returns_none_metrics(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        results = [BacktestResult(ticker="X", trade_date="2024-01-01", rating="Buy", direction=1)]
        with patch("tradingagents.backtesting.report.fetch_returns", return_value=(None, None, None)):
            summary = BacktestReport(results).compute(hold_days_override=5)

        assert summary.win_rate is None
        assert summary.total_return is None
        assert summary.error_count == 1

    def test_error_results_excluded_from_metrics(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        results = [
            BacktestResult(ticker="NVDA", trade_date="2024-01-01", rating="Buy", direction=1),
            BacktestResult(ticker="NVDA", trade_date="2024-02-01", error="timeout"),
        ]
        with patch("tradingagents.backtesting.report.fetch_returns", return_value=(0.05, 0.02, 21)):
            summary = BacktestReport(results).compute(hold_days_override=21)

        assert summary.error_count >= 1
        assert "Buy" in summary.signal_counts

    def test_equity_curve_starts_at_one(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        with patch("tradingagents.backtesting.report.fetch_returns", side_effect=_return_map):
            summary = BacktestReport(_make_results()).compute(hold_days_override=21)

        assert summary.cumulative_equity[0] == pytest.approx(1.0)
        assert len(summary.cumulative_equity) > 1

    def test_max_drawdown_non_positive(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        with patch("tradingagents.backtesting.report.fetch_returns", side_effect=_return_map):
            summary = BacktestReport(_make_results()).compute(hold_days_override=21)

        assert summary.max_drawdown is not None
        assert summary.max_drawdown <= 0.0
