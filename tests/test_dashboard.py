"""Tests for tradingagents.dashboard.builder."""

import tempfile
import os

from tradingagents.backtest.models import TradeRecord, PerformanceMetrics, BacktestResult
from tradingagents.dashboard.builder import DashboardBuilder


def _make_metrics():
    return PerformanceMetrics(
        total_trades=10, win_rate=70.0, avg_return=5.0,
        cumulative_return=23.4, sharpe_ratio=1.42, max_drawdown=-8.7,
        max_drawdown_duration=15, alpha=5.2, beta=0.87,
        profit_factor=1.83, avg_holding_days=12.3,
        equity_curve=[
            {"date": "2024-04-01", "equity": 100000, "drawdown": 0.0},
            {"date": "2024-05-01", "equity": 105000, "drawdown": 0.0},
            {"date": "2024-06-01", "equity": 102000, "drawdown": -2.86},
            {"date": "2024-07-01", "equity": 112000, "drawdown": 0.0},
        ],
        monthly_returns=[
            {"month": "2024-04", "return_pct": 5.0},
            {"month": "2024-05", "return_pct": -2.86},
            {"month": "2024-06", "return_pct": 9.8},
        ],
    )


def _make_trades():
    return [
        TradeRecord(
            ticker="NVDA", trade_date="2024-04-01", signal="BUY",
            entry_price=100.0, quantity=100, source="backtest",
            exit_price=110.0, exit_date="2024-05-01",
            pnl=1000.0, pnl_pct=10.0,
            debate_summary="Bull: strong AI demand\nBear: high valuation",
            risk_decision="Risk acceptable",
        ),
        TradeRecord(
            ticker="NVDA", trade_date="2024-05-01", signal="BUY",
            entry_price=110.0, quantity=100, source="backtest",
            exit_price=105.0, exit_date="2024-06-01",
            pnl=-500.0, pnl_pct=-4.55,
        ),
    ]


class TestDashboardBuilder:
    def test_build_creates_html_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = DashboardBuilder(output_dir=tmp)
            path = builder.build(
                metrics=_make_metrics(),
                trades=_make_trades(),
                title="Test Dashboard",
            )
            assert os.path.exists(path)
            assert path.endswith(".html")

    def test_html_contains_kpi_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = DashboardBuilder(output_dir=tmp)
            path = builder.build(metrics=_make_metrics(), trades=_make_trades())
            with open(path) as f:
                html = f.read()
            assert "23.4" in html
            assert "1.42" in html
            assert "-8.7" in html
            assert "70.0" in html

    def test_html_contains_plotly(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = DashboardBuilder(output_dir=tmp)
            path = builder.build(metrics=_make_metrics(), trades=_make_trades())
            with open(path) as f:
                html = f.read()
            assert "plotly" in html.lower()

    def test_html_contains_trade_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = DashboardBuilder(output_dir=tmp)
            path = builder.build(metrics=_make_metrics(), trades=_make_trades())
            with open(path) as f:
                html = f.read()
            assert "NVDA" in html
            assert "BUY" in html

    def test_backtest_comparison_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            bt = BacktestResult(
                ticker="NVDA",
                config_snapshot={"persona": "warren_buffett"},
                start_date="2024-04-01", end_date="2025-04-01",
                benchmark="SPY", trades=[], metrics=_make_metrics(),
            )
            builder = DashboardBuilder(output_dir=tmp)
            path = builder.build(
                metrics=_make_metrics(), trades=_make_trades(),
                backtest_results=[bt],
            )
            with open(path) as f:
                html = f.read()
            assert "backtest" in html.lower() or "Backtest" in html

    def test_empty_trades(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = DashboardBuilder(output_dir=tmp)
            metrics = PerformanceMetrics(
                total_trades=0, win_rate=0.0, avg_return=0.0,
                cumulative_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                max_drawdown_duration=0, alpha=0.0, beta=0.0,
                profit_factor=0.0, avg_holding_days=0.0,
                equity_curve=[], monthly_returns=[],
            )
            path = builder.build(metrics=metrics, trades=[])
            assert os.path.exists(path)
