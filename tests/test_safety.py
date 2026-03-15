"""Tests for tradingagents.execution.safety."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from tradingagents.execution.safety import SafetyGuard, KST
from tradingagents.execution.models import (
    OrderRequest,
    OrderSide,
    OrderType,
    AccountBalance,
    PortfolioSnapshot,
    Position,
)


def _make_config(mode="paper", safety_overrides=None):
    safety = {
        "max_position_pct": 0.10,
        "max_order_amount": 5_000_000,
        "daily_loss_limit": -500_000,
        "enforce_market_hours": True,
    }
    if safety_overrides:
        safety.update(safety_overrides)
    return {"broker": {"mode": mode, "safety": safety}}


def _make_portfolio(total_equity=10_000_000):
    bal = AccountBalance(
        total_equity=total_equity,
        cash_balance=total_equity,
        buying_power=total_equity,
        total_unrealized_pnl=0,
    )
    return PortfolioSnapshot(account_no="12345678-01", balance=bal)


class TestCheckMarketHours:
    def test_paper_trading_bypasses(self):
        guard = SafetyGuard(_make_config(mode="paper"))
        ok, msg = guard.check_market_hours()
        assert ok is True
        assert "Paper" in msg

    def test_real_trading_enforcement_disabled(self):
        guard = SafetyGuard(
            _make_config(mode="real", safety_overrides={"enforce_market_hours": False})
        )
        ok, msg = guard.check_market_hours()
        assert ok is True
        assert "disabled" in msg

    def test_real_trading_weekday_market_open(self):
        guard = SafetyGuard(_make_config(mode="real"))
        # Wednesday 10:00 KST
        mock_time = datetime(2026, 3, 11, 10, 0, 0, tzinfo=KST)
        with patch("tradingagents.execution.safety.datetime") as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            ok, msg = guard.check_market_hours()
        assert ok is True

    def test_real_trading_weekend_blocked(self):
        guard = SafetyGuard(_make_config(mode="real"))
        # Saturday 10:00 KST
        mock_time = datetime(2026, 3, 14, 10, 0, 0, tzinfo=KST)
        with patch("tradingagents.execution.safety.datetime") as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            ok, msg = guard.check_market_hours()
        assert ok is False
        assert "weekend" in msg.lower()

    def test_real_trading_before_open(self):
        guard = SafetyGuard(_make_config(mode="real"))
        # Wednesday 08:30 KST
        mock_time = datetime(2026, 3, 11, 8, 30, 0, tzinfo=KST)
        with patch("tradingagents.execution.safety.datetime") as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            ok, msg = guard.check_market_hours()
        assert ok is False
        assert "not yet open" in msg.lower()

    def test_real_trading_after_close(self):
        guard = SafetyGuard(_make_config(mode="real"))
        # Wednesday 16:00 KST
        mock_time = datetime(2026, 3, 11, 16, 0, 0, tzinfo=KST)
        with patch("tradingagents.execution.safety.datetime") as mock_dt:
            mock_dt.now.return_value = mock_time
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            ok, msg = guard.check_market_hours()
        assert ok is False
        assert "closed" in msg.lower()


class TestCheckPositionSize:
    def test_within_limit(self):
        guard = SafetyGuard(_make_config())
        portfolio = _make_portfolio(total_equity=10_000_000)
        ok, msg = guard.check_position_size(500_000, portfolio)
        assert ok is True

    def test_exceeds_limit(self):
        guard = SafetyGuard(_make_config())
        portfolio = _make_portfolio(total_equity=10_000_000)
        # 1.5M = 15% > 10% limit
        ok, msg = guard.check_position_size(1_500_000, portfolio)
        assert ok is False
        assert "exceeds" in msg.lower()

    def test_zero_equity_skips(self):
        guard = SafetyGuard(_make_config())
        portfolio = _make_portfolio(total_equity=0)
        ok, msg = guard.check_position_size(1_000_000, portfolio)
        assert ok is True


class TestCheckOrderAmount:
    def test_within_limit(self):
        guard = SafetyGuard(_make_config())
        ok, msg = guard.check_order_amount(3_000_000)
        assert ok is True

    def test_exceeds_limit(self):
        guard = SafetyGuard(_make_config())
        ok, msg = guard.check_order_amount(6_000_000)
        assert ok is False
        assert "exceeds" in msg.lower()

    def test_exact_limit(self):
        guard = SafetyGuard(_make_config())
        ok, msg = guard.check_order_amount(5_000_000)
        assert ok is True


class TestCheckDailyLoss:
    def test_within_limit(self):
        guard = SafetyGuard(_make_config())
        ok, msg = guard.check_daily_loss(-200_000)
        assert ok is True

    def test_exceeds_limit(self):
        guard = SafetyGuard(_make_config())
        ok, msg = guard.check_daily_loss(-600_000)
        assert ok is False
        assert "exceeds" in msg.lower()

    def test_positive_pnl(self):
        guard = SafetyGuard(_make_config())
        ok, msg = guard.check_daily_loss(1_000_000)
        assert ok is True


class TestValidateAll:
    def test_all_pass(self):
        guard = SafetyGuard(_make_config(mode="paper"))
        order = OrderRequest(ticker="005930", side=OrderSide.BUY, quantity=10)
        portfolio = _make_portfolio(total_equity=10_000_000)
        ok, msg = guard.validate_all(order, price=70000, portfolio=portfolio, daily_pnl=0)
        assert ok is True
        assert "All safety checks passed" in msg

    def test_order_amount_fails(self):
        guard = SafetyGuard(_make_config(mode="paper"))
        order = OrderRequest(ticker="005930", side=OrderSide.BUY, quantity=100)
        portfolio = _make_portfolio(total_equity=100_000_000)
        # 100 * 70000 = 7M > 5M limit
        ok, msg = guard.validate_all(order, price=70000, portfolio=portfolio, daily_pnl=0)
        assert ok is False

    def test_first_failure_returns(self):
        """validate_all should stop at the first failure."""
        guard = SafetyGuard(_make_config(mode="paper"))
        order = OrderRequest(ticker="005930", side=OrderSide.BUY, quantity=200)
        portfolio = _make_portfolio(total_equity=10_000_000)
        # Both order amount (14M) and position size will fail
        ok, msg = guard.validate_all(order, price=70000, portfolio=portfolio, daily_pnl=-600_000)
        assert ok is False
