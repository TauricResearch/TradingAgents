"""Tests for tradingagents.execution.models."""

from datetime import datetime

from tradingagents.execution.models import (
    OrderSide,
    OrderType,
    OrderStatus,
    OrderRequest,
    OrderResult,
    Position,
    AccountBalance,
    PortfolioSnapshot,
)


class TestEnums:
    def test_order_side_values(self):
        assert OrderSide.BUY == "BUY"
        assert OrderSide.SELL == "SELL"

    def test_order_type_values(self):
        assert OrderType.MARKET == "MARKET"
        assert OrderType.LIMIT == "LIMIT"

    def test_order_status_values(self):
        assert OrderStatus.PENDING == "PENDING"
        assert OrderStatus.FILLED == "FILLED"
        assert OrderStatus.PARTIALLY_FILLED == "PARTIALLY_FILLED"
        assert OrderStatus.REJECTED == "REJECTED"
        assert OrderStatus.CANCELLED == "CANCELLED"

    def test_enums_are_str(self):
        """Enums should be usable as strings (str, Enum)."""
        assert isinstance(OrderSide.BUY, str)
        assert OrderSide.BUY == "BUY"
        assert str(OrderSide.BUY) == "OrderSide.BUY" or OrderSide.BUY.value == "BUY"


class TestOrderRequest:
    def test_defaults(self):
        req = OrderRequest(ticker="005930", side=OrderSide.BUY, quantity=10)
        assert req.order_type == OrderType.MARKET
        assert req.limit_price is None
        assert req.account_no is None

    def test_limit_order(self):
        req = OrderRequest(
            ticker="005930",
            side=OrderSide.SELL,
            quantity=5,
            order_type=OrderType.LIMIT,
            limit_price=70000.0,
        )
        assert req.order_type == OrderType.LIMIT
        assert req.limit_price == 70000.0


class TestOrderResult:
    def test_defaults(self):
        result = OrderResult(success=True)
        assert result.order_id is None
        assert result.status == OrderStatus.PENDING
        assert result.filled_quantity == 0
        assert result.filled_price == 0.0
        assert result.message == ""
        assert isinstance(result.timestamp, datetime)
        assert result.raw_response is None

    def test_filled_result(self):
        result = OrderResult(
            success=True,
            order_id="ORD001",
            status=OrderStatus.FILLED,
            filled_quantity=100,
            filled_price=70000.0,
            message="Order filled",
        )
        assert result.success is True
        assert result.filled_quantity == 100


class TestPosition:
    def test_creation(self):
        pos = Position(
            ticker="005930",
            name="삼성전자",
            quantity=100,
            avg_cost=70000.0,
            current_price=73500.0,
            unrealized_pnl=350000.0,
            unrealized_pnl_pct=5.0,
            market_value=7350000.0,
        )
        assert pos.ticker == "005930"
        assert pos.name == "삼성전자"
        assert pos.quantity == 100


class TestAccountBalance:
    def test_defaults(self):
        bal = AccountBalance(
            total_equity=10_000_000,
            cash_balance=5_000_000,
            buying_power=5_000_000,
            total_unrealized_pnl=500_000,
        )
        assert bal.currency == "KRW"

    def test_custom_currency(self):
        bal = AccountBalance(
            total_equity=10000,
            cash_balance=5000,
            buying_power=5000,
            total_unrealized_pnl=0,
            currency="USD",
        )
        assert bal.currency == "USD"


class TestPortfolioSnapshot:
    def test_empty_positions(self):
        bal = AccountBalance(
            total_equity=10_000_000,
            cash_balance=10_000_000,
            buying_power=10_000_000,
            total_unrealized_pnl=0,
        )
        snap = PortfolioSnapshot(account_no="12345678-01", balance=bal)
        assert snap.positions == []
        assert isinstance(snap.snapshot_time, datetime)

    def test_with_positions(self):
        pos = Position(
            ticker="005930", name="삼성전자", quantity=10,
            avg_cost=70000, current_price=71000,
            unrealized_pnl=10000, unrealized_pnl_pct=1.43,
            market_value=710000,
        )
        bal = AccountBalance(
            total_equity=10_710_000, cash_balance=10_000_000,
            buying_power=10_000_000, total_unrealized_pnl=10000,
        )
        snap = PortfolioSnapshot(
            account_no="12345678-01", balance=bal, positions=[pos]
        )
        assert len(snap.positions) == 1
        assert snap.positions[0].ticker == "005930"
