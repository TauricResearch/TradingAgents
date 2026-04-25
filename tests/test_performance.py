"""Tests for tradingagents.backtest.performance."""

import pytest
from tradingagents.backtest.models import TradeRecord
from tradingagents.backtest.performance import PerformanceCalculator


def _make_trades():
    """10 trades: 7 wins, 3 losses."""
    data = [
        ("2024-04-01", "BUY", 100.0, "2024-05-01", 110.0),   # +10%
        ("2024-05-01", "BUY", 200.0, "2024-06-01", 190.0),   # -5%
        ("2024-06-01", "BUY", 150.0, "2024-07-01", 165.0),   # +10%
        ("2024-07-01", "BUY", 120.0, "2024-08-01", 132.0),   # +10%
        ("2024-08-01", "BUY", 180.0, "2024-09-01", 171.0),   # -5%
        ("2024-09-01", "BUY", 140.0, "2024-10-01", 154.0),   # +10%
        ("2024-10-01", "BUY", 160.0, "2024-11-01", 176.0),   # +10%
        ("2024-11-01", "BUY", 130.0, "2024-12-01", 117.0),   # -10%
        ("2024-12-01", "BUY", 170.0, "2025-01-01", 187.0),   # +10%
        ("2025-01-01", "BUY", 190.0, "2025-02-01", 209.0),   # +10%
    ]
    trades = []
    for entry_date, signal, entry_p, exit_date, exit_p in data:
        pnl_pct = (exit_p - entry_p) / entry_p * 100
        trades.append(TradeRecord(
            ticker="TEST", trade_date=entry_date, signal=signal,
            entry_price=entry_p, quantity=100, source="backtest",
            exit_price=exit_p, exit_date=exit_date,
            pnl=(exit_p - entry_p) * 100, pnl_pct=pnl_pct,
        ))
    return trades


class TestPerformanceCalculator:
    def test_basic_metrics(self):
        calc = PerformanceCalculator()
        trades = _make_trades()
        metrics = calc.calculate(
            trades=trades, initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert metrics.total_trades == 10
        assert metrics.win_rate == 70.0
        assert metrics.avg_return == pytest.approx(5.0, abs=0.1)

    def test_sharpe_positive(self):
        calc = PerformanceCalculator()
        metrics = calc.calculate(
            trades=_make_trades(), initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert metrics.sharpe_ratio > 0

    def test_max_drawdown_negative(self):
        calc = PerformanceCalculator()
        metrics = calc.calculate(
            trades=_make_trades(), initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert metrics.max_drawdown < 0

    def test_equity_curve_not_empty(self):
        calc = PerformanceCalculator()
        metrics = calc.calculate(
            trades=_make_trades(), initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert len(metrics.equity_curve) > 0
        assert "date" in metrics.equity_curve[0]
        assert "equity" in metrics.equity_curve[0]

    def test_monthly_returns_not_empty(self):
        calc = PerformanceCalculator()
        metrics = calc.calculate(
            trades=_make_trades(), initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert len(metrics.monthly_returns) > 0

    def test_empty_trades(self):
        calc = PerformanceCalculator()
        metrics = calc.calculate(
            trades=[], initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.sharpe_ratio == 0.0

    def test_profit_factor(self):
        calc = PerformanceCalculator()
        metrics = calc.calculate(
            trades=_make_trades(), initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert metrics.profit_factor > 1.0
