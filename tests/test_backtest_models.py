"""Tests for tradingagents.backtest.models."""

from tradingagents.backtest.models import (
    TradeRecord,
    PerformanceMetrics,
    BacktestResult,
)


class TestTradeRecord:
    def test_creation_with_defaults(self):
        rec = TradeRecord(
            ticker="005930",
            trade_date="2026-01-15",
            signal="BUY",
            entry_price=58000.0,
            quantity=100,
            source="backtest",
        )
        assert rec.ticker == "005930"
        assert rec.signal == "BUY"
        assert rec.exit_price is None
        assert rec.exit_date is None
        assert rec.pnl is None
        assert rec.pnl_pct is None
        assert rec.analyst_reports == {}
        assert rec.debate_summary == ""
        assert rec.risk_decision == ""
        assert rec.persona is None

    def test_closed_trade(self):
        rec = TradeRecord(
            ticker="NVDA",
            trade_date="2026-01-15",
            signal="BUY",
            entry_price=100.0,
            quantity=50,
            source="paper",
            exit_price=110.0,
            exit_date="2026-02-15",
            pnl=500.0,
            pnl_pct=10.0,
        )
        assert rec.exit_price == 110.0
        assert rec.pnl == 500.0
        assert rec.pnl_pct == 10.0

    def test_to_dict(self):
        rec = TradeRecord(
            ticker="005930",
            trade_date="2026-01-15",
            signal="BUY",
            entry_price=58000.0,
            quantity=100,
            source="backtest",
        )
        d = rec.to_dict()
        assert d["ticker"] == "005930"
        assert isinstance(d, dict)

    def test_from_dict(self):
        d = {
            "ticker": "005930",
            "trade_date": "2026-01-15",
            "signal": "BUY",
            "entry_price": 58000.0,
            "quantity": 100,
            "source": "backtest",
        }
        rec = TradeRecord.from_dict(d)
        assert rec.ticker == "005930"
        assert rec.entry_price == 58000.0

    def test_source_validation(self):
        import pytest
        with pytest.raises(ValueError):
            TradeRecord(
                ticker="X", trade_date="2026-01-01", signal="BUY",
                entry_price=1.0, quantity=1, source="invalid",
            )

    def test_signal_validation(self):
        import pytest
        with pytest.raises(ValueError):
            TradeRecord(
                ticker="X", trade_date="2026-01-01", signal="MAYBE",
                entry_price=1.0, quantity=1, source="backtest",
            )


class TestPerformanceMetrics:
    def test_creation(self):
        m = PerformanceMetrics(
            total_trades=20,
            win_rate=65.0,
            avg_return=2.1,
            cumulative_return=23.4,
            sharpe_ratio=1.42,
            max_drawdown=-8.7,
            max_drawdown_duration=15,
            alpha=5.2,
            beta=0.87,
            profit_factor=1.83,
            avg_holding_days=12.3,
            equity_curve=[{"date": "2026-01-01", "equity": 100000, "drawdown": 0.0}],
            monthly_returns=[{"month": "2026-01", "return_pct": 2.1}],
        )
        assert m.sharpe_ratio == 1.42
        assert m.max_drawdown == -8.7
        assert len(m.equity_curve) == 1

    def test_to_dict(self):
        m = PerformanceMetrics(
            total_trades=10, win_rate=50.0, avg_return=1.0,
            cumulative_return=10.0, sharpe_ratio=1.0, max_drawdown=-5.0,
            max_drawdown_duration=5, alpha=2.0, beta=1.0,
            profit_factor=1.5, avg_holding_days=10.0,
            equity_curve=[], monthly_returns=[],
        )
        d = m.to_dict()
        assert d["sharpe_ratio"] == 1.0


class TestBacktestResult:
    def test_creation(self):
        metrics = PerformanceMetrics(
            total_trades=1, win_rate=100.0, avg_return=5.0,
            cumulative_return=5.0, sharpe_ratio=2.0, max_drawdown=-1.0,
            max_drawdown_duration=1, alpha=3.0, beta=0.5,
            profit_factor=5.0, avg_holding_days=30.0,
            equity_curve=[], monthly_returns=[],
        )
        result = BacktestResult(
            ticker="NVDA",
            config_snapshot={"llm_provider": "anthropic", "persona": "warren_buffett"},
            start_date="2024-04-01",
            end_date="2026-04-01",
            benchmark="SPY",
            trades=[],
            metrics=metrics,
        )
        assert result.ticker == "NVDA"
        assert result.benchmark == "SPY"
        assert result.created_at is not None
