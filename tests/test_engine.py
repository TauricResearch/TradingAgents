"""Tests for tradingagents.execution.engine."""

from unittest.mock import MagicMock, patch, PropertyMock

from tradingagents.execution.engine import ExecutionEngine
from tradingagents.execution.models import (
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    AccountBalance,
    PortfolioSnapshot,
    Position,
)


def _make_config(**overrides):
    config = {
        "broker": {
            "enabled": True,
            "mode": "paper",
            "default_order_type": "market",
            "default_quantity": None,
            "default_position_pct": 0.05,
            "safety": {
                "max_position_pct": 0.10,
                "max_order_amount": 5_000_000,
                "daily_loss_limit": -500_000,
                "enforce_market_hours": True,
            },
        }
    }
    config["broker"].update(overrides)
    return config


def _make_portfolio(total_equity=10_000_000, positions=None):
    bal = AccountBalance(
        total_equity=total_equity,
        cash_balance=total_equity,
        buying_power=total_equity,
        total_unrealized_pnl=0,
    )
    return PortfolioSnapshot(
        account_no="12345678-01", balance=bal, positions=positions or []
    )


def _make_broker(price=70000, portfolio=None):
    broker = MagicMock()
    type(broker).is_paper_trading = PropertyMock(return_value=True)
    broker.get_current_price.return_value = price
    broker.get_portfolio.return_value = portfolio or _make_portfolio()
    broker.place_order.return_value = OrderResult(
        success=True,
        order_id="ORD001",
        status=OrderStatus.FILLED,
        filled_quantity=10,
        filled_price=price,
        message="Order filled",
    )
    return broker


class TestHoldDecision:
    def test_hold_returns_success(self):
        engine = ExecutionEngine(_make_broker(), _make_config())
        result = engine.execute_decision("005930", "HOLD")
        assert result.success is True
        assert result.status == OrderStatus.FILLED
        assert "HOLD" in result.message

    def test_hold_case_insensitive(self):
        engine = ExecutionEngine(_make_broker(), _make_config())
        result = engine.execute_decision("005930", "  hold  ")
        assert result.success is True

    def test_hold_no_broker_call(self):
        broker = _make_broker()
        engine = ExecutionEngine(broker, _make_config())
        engine.execute_decision("005930", "HOLD")
        broker.place_order.assert_not_called()


class TestInvalidDecision:
    def test_invalid_decision_rejected(self):
        engine = ExecutionEngine(_make_broker(), _make_config())
        result = engine.execute_decision("005930", "MAYBE")
        assert result.success is False
        assert result.status == OrderStatus.REJECTED
        assert "Invalid" in result.message

    def test_empty_decision_rejected(self):
        engine = ExecutionEngine(_make_broker(), _make_config())
        result = engine.execute_decision("005930", "")
        assert result.success is False


class TestBuyDecision:
    def test_buy_with_explicit_quantity(self):
        broker = _make_broker(price=70000)
        engine = ExecutionEngine(broker, _make_config())
        result = engine.execute_decision("005930", "BUY", quantity=10)
        assert result.success is True
        broker.place_order.assert_called_once()
        order = broker.place_order.call_args[0][0]
        assert order.side == OrderSide.BUY
        assert order.quantity == 10

    def test_buy_calculates_quantity_from_portfolio(self):
        portfolio = _make_portfolio(total_equity=10_000_000)
        broker = _make_broker(price=50000, portfolio=portfolio)
        config = _make_config(default_position_pct=0.05)
        engine = ExecutionEngine(broker, config)
        result = engine.execute_decision("005930", "BUY")
        assert result.success is True
        order = broker.place_order.call_args[0][0]
        # 10M * 0.05 / 50000 = 10 shares
        assert order.quantity == 10

    def test_buy_uses_default_quantity(self):
        broker = _make_broker(price=70000)
        config = _make_config(default_quantity=5)
        engine = ExecutionEngine(broker, config)
        result = engine.execute_decision("005930", "BUY")
        order = broker.place_order.call_args[0][0]
        assert order.quantity == 5


class TestSellDecision:
    def test_sell_uses_held_quantity(self):
        pos = Position(
            ticker="005930", name="삼성전자", quantity=50,
            avg_cost=65000, current_price=70000,
            unrealized_pnl=250000, unrealized_pnl_pct=7.7,
            market_value=3500000,
        )
        portfolio = _make_portfolio(total_equity=100_000_000, positions=[pos])
        broker = _make_broker(price=70000, portfolio=portfolio)
        engine = ExecutionEngine(broker, _make_config())
        result = engine.execute_decision("005930", "SELL")
        assert result.success is True
        order = broker.place_order.call_args[0][0]
        assert order.side == OrderSide.SELL
        assert order.quantity == 50

    def test_sell_no_position_returns_zero_quantity(self):
        portfolio = _make_portfolio(total_equity=10_000_000, positions=[])
        broker = _make_broker(price=70000, portfolio=portfolio)
        engine = ExecutionEngine(broker, _make_config())
        result = engine.execute_decision("005930", "SELL")
        assert result.success is False
        assert "quantity is 0" in result.message.lower()


class TestPriceErrors:
    def test_zero_price_rejected(self):
        broker = _make_broker(price=0)
        engine = ExecutionEngine(broker, _make_config())
        result = engine.execute_decision("005930", "BUY", quantity=10)
        assert result.success is False
        assert "Invalid price" in result.message

    def test_price_exception_handled(self):
        broker = _make_broker()
        broker.get_current_price.side_effect = RuntimeError("API error")
        engine = ExecutionEngine(broker, _make_config())
        result = engine.execute_decision("005930", "BUY", quantity=10)
        assert result.success is False
        assert "Failed to get price" in result.message


class TestSafetyIntegration:
    def test_order_amount_exceeds_safety(self):
        broker = _make_broker(price=70000)
        engine = ExecutionEngine(broker, _make_config())
        # 100 * 70000 = 7M > 5M limit
        result = engine.execute_decision("005930", "BUY", quantity=100)
        assert result.success is False
        assert "Safety check failed" in result.message
        broker.place_order.assert_not_called()


class TestGetPortfolioContext:
    def test_portfolio_context_format(self):
        pos = Position(
            ticker="005930", name="삼성전자", quantity=100,
            avg_cost=70000, current_price=73500,
            unrealized_pnl=350000, unrealized_pnl_pct=5.0,
            market_value=7350000,
        )
        portfolio = _make_portfolio(total_equity=17_350_000, positions=[pos])
        broker = _make_broker(portfolio=portfolio)
        engine = ExecutionEngine(broker, _make_config())

        ctx = engine.get_portfolio_context()
        assert "Paper" in ctx
        assert "삼성전자" in ctx
        assert "005930" in ctx
        assert "100 shares" in ctx

    def test_portfolio_context_no_positions(self):
        broker = _make_broker(portfolio=_make_portfolio())
        engine = ExecutionEngine(broker, _make_config())
        ctx = engine.get_portfolio_context()
        assert "No current positions" in ctx

    def test_portfolio_context_broker_error(self):
        broker = _make_broker()
        broker.get_portfolio.side_effect = RuntimeError("Connection failed")
        engine = ExecutionEngine(broker, _make_config())
        ctx = engine.get_portfolio_context()
        assert "unavailable" in ctx.lower()


class TestOrderHistory:
    def test_order_history_tracked(self):
        broker = _make_broker(price=50000)
        engine = ExecutionEngine(broker, _make_config())
        engine.execute_decision("005930", "BUY", quantity=10)
        engine.execute_decision("005930", "BUY", quantity=5)
        assert len(engine._order_history) == 2
