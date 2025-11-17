"""
Comprehensive tests for base broker interface.

Tests order data structures, enumerations, convenience methods,
and abstract interface compliance.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from abc import ABC

from tradingagents.brokers.base import (
    BaseBroker,
    BrokerOrder,
    BrokerPosition,
    BrokerAccount,
    OrderSide,
    OrderType,
    OrderStatus,
    BrokerError,
    ConnectionError,
    OrderError,
    InsufficientFundsError,
)


class TestOrderEnumerations:
    """Test order-related enumerations."""

    def test_order_side_values(self):
        """Test OrderSide enumeration values."""
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"

    def test_order_type_values(self):
        """Test OrderType enumeration values."""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"
        assert OrderType.STOP_LIMIT.value == "stop_limit"

    def test_order_status_values(self):
        """Test OrderStatus enumeration values."""
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.SUBMITTED.value == "submitted"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.PARTIALLY_FILLED.value == "partially_filled"
        assert OrderStatus.CANCELLED.value == "cancelled"
        assert OrderStatus.REJECTED.value == "rejected"


class TestBrokerOrder:
    """Test BrokerOrder dataclass."""

    def test_create_market_buy_order(self):
        """Test creating a market buy order."""
        order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET
        )

        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.quantity == Decimal("100")
        assert order.order_type == OrderType.MARKET
        assert order.status == OrderStatus.PENDING
        assert order.time_in_force == "day"
        assert order.order_id is None
        assert order.filled_qty == Decimal("0")

    def test_create_limit_sell_order(self):
        """Test creating a limit sell order."""
        order = BrokerOrder(
            symbol="TSLA",
            side=OrderSide.SELL,
            quantity=Decimal("50"),
            order_type=OrderType.LIMIT,
            limit_price=Decimal("250.50")
        )

        assert order.symbol == "TSLA"
        assert order.side == OrderSide.SELL
        assert order.limit_price == Decimal("250.50")

    def test_create_stop_loss_order(self):
        """Test creating a stop-loss order."""
        order = BrokerOrder(
            symbol="NVDA",
            side=OrderSide.SELL,
            quantity=Decimal("25"),
            order_type=OrderType.STOP,
            stop_price=Decimal("800.00")
        )

        assert order.stop_price == Decimal("800.00")
        assert order.order_type == OrderType.STOP

    def test_create_stop_limit_order(self):
        """Test creating a stop-limit order."""
        order = BrokerOrder(
            symbol="AMD",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.STOP_LIMIT,
            stop_price=Decimal("140.00"),
            limit_price=Decimal("142.00")
        )

        assert order.stop_price == Decimal("140.00")
        assert order.limit_price == Decimal("142.00")

    def test_order_with_custom_time_in_force(self):
        """Test order with custom time_in_force."""
        order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET,
            time_in_force="gtc"
        )

        assert order.time_in_force == "gtc"

    def test_order_with_filled_data(self):
        """Test order with filled data."""
        filled_at = datetime.now()
        order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET,
            order_id="order-123",
            status=OrderStatus.FILLED,
            filled_qty=Decimal("100"),
            filled_price=Decimal("150.25"),
            filled_at=filled_at
        )

        assert order.order_id == "order-123"
        assert order.status == OrderStatus.FILLED
        assert order.filled_qty == Decimal("100")
        assert order.filled_price == Decimal("150.25")
        assert order.filled_at == filled_at


class TestBrokerPosition:
    """Test BrokerPosition dataclass."""

    def test_create_position(self):
        """Test creating a broker position."""
        position = BrokerPosition(
            symbol="AAPL",
            quantity=Decimal("100"),
            avg_entry_price=Decimal("150.00"),
            current_price=Decimal("155.00"),
            market_value=Decimal("15500.00"),
            unrealized_pnl=Decimal("500.00"),
            unrealized_pnl_percent=Decimal("0.0333"),
            cost_basis=Decimal("15000.00")
        )

        assert position.symbol == "AAPL"
        assert position.quantity == Decimal("100")
        assert position.avg_entry_price == Decimal("150.00")
        assert position.current_price == Decimal("155.00")
        assert position.market_value == Decimal("15500.00")
        assert position.unrealized_pnl == Decimal("500.00")
        assert position.unrealized_pnl_percent == Decimal("0.0333")
        assert position.cost_basis == Decimal("15000.00")

    def test_position_with_loss(self):
        """Test position with unrealized loss."""
        position = BrokerPosition(
            symbol="TSLA",
            quantity=Decimal("50"),
            avg_entry_price=Decimal("250.00"),
            current_price=Decimal("240.00"),
            market_value=Decimal("12000.00"),
            unrealized_pnl=Decimal("-500.00"),
            unrealized_pnl_percent=Decimal("-0.04"),
            cost_basis=Decimal("12500.00")
        )

        assert position.unrealized_pnl < 0
        assert position.unrealized_pnl_percent < 0


class TestBrokerAccount:
    """Test BrokerAccount dataclass."""

    def test_create_account(self):
        """Test creating a broker account."""
        account = BrokerAccount(
            account_number="ACC123456",
            cash=Decimal("50000.00"),
            buying_power=Decimal("200000.00"),
            portfolio_value=Decimal("75000.00"),
            equity=Decimal("75000.00"),
            last_equity=Decimal("74500.00"),
            multiplier=Decimal("4"),
            currency="USD",
            pattern_day_trader=False
        )

        assert account.account_number == "ACC123456"
        assert account.cash == Decimal("50000.00")
        assert account.buying_power == Decimal("200000.00")
        assert account.portfolio_value == Decimal("75000.00")
        assert account.currency == "USD"
        assert account.pattern_day_trader is False

    def test_account_defaults(self):
        """Test account with default values."""
        account = BrokerAccount(
            account_number="ACC123456",
            cash=Decimal("50000.00"),
            buying_power=Decimal("50000.00"),
            portfolio_value=Decimal("50000.00"),
            equity=Decimal("50000.00"),
            last_equity=Decimal("50000.00"),
            multiplier=Decimal("1")
        )

        # Default values
        assert account.currency == "USD"
        assert account.pattern_day_trader is False

    def test_account_with_pdt_status(self):
        """Test account with pattern day trader status."""
        account = BrokerAccount(
            account_number="ACC123456",
            cash=Decimal("30000.00"),
            buying_power=Decimal("120000.00"),
            portfolio_value=Decimal("50000.00"),
            equity=Decimal("50000.00"),
            last_equity=Decimal("49000.00"),
            multiplier=Decimal("4"),
            pattern_day_trader=True
        )

        assert account.pattern_day_trader is True
        assert account.multiplier == Decimal("4")


class TestBrokerExceptions:
    """Test broker exception classes."""

    def test_broker_error(self):
        """Test BrokerError exception."""
        with pytest.raises(BrokerError, match="Test error"):
            raise BrokerError("Test error")

    def test_connection_error(self):
        """Test ConnectionError exception."""
        with pytest.raises(ConnectionError, match="Connection failed"):
            raise ConnectionError("Connection failed")

        # Should also be a BrokerError
        with pytest.raises(BrokerError):
            raise ConnectionError("Connection failed")

    def test_order_error(self):
        """Test OrderError exception."""
        with pytest.raises(OrderError, match="Order failed"):
            raise OrderError("Order failed")

        # Should also be a BrokerError
        with pytest.raises(BrokerError):
            raise OrderError("Order failed")

    def test_insufficient_funds_error(self):
        """Test InsufficientFundsError exception."""
        with pytest.raises(InsufficientFundsError, match="Insufficient funds"):
            raise InsufficientFundsError("Insufficient funds")

        # Should also be a BrokerError
        with pytest.raises(BrokerError):
            raise InsufficientFundsError("Insufficient funds")


class TestBaseBrokerInterface:
    """Test BaseBroker abstract interface."""

    def test_base_broker_is_abstract(self):
        """Test that BaseBroker cannot be instantiated directly."""
        # BaseBroker is abstract and should not be instantiable
        assert ABC in BaseBroker.__bases__

    def test_base_broker_paper_trading_flag(self):
        """Test that BaseBroker stores paper_trading flag."""
        # Create a concrete implementation for testing
        class ConcreteBroker(BaseBroker):
            def connect(self): return True
            def disconnect(self): pass
            def get_account(self): pass
            def get_positions(self): pass
            def get_position(self, symbol): pass
            def submit_order(self, order): pass
            def cancel_order(self, order_id): pass
            def get_order(self, order_id): pass
            def get_orders(self, status=None, limit=50): pass
            def get_current_price(self, symbol): pass

        broker = ConcreteBroker(paper_trading=True)
        assert broker.paper_trading is True

        broker = ConcreteBroker(paper_trading=False)
        assert broker.paper_trading is False


class TestBaseBrokerConvenienceMethods:
    """Test convenience methods in BaseBroker."""

    class MockBroker(BaseBroker):
        """Mock broker for testing convenience methods."""

        def __init__(self):
            super().__init__(paper_trading=True)
            self.submitted_orders = []

        def connect(self): return True
        def disconnect(self): pass
        def get_account(self): pass
        def get_positions(self): pass
        def get_position(self, symbol): pass

        def submit_order(self, order):
            self.submitted_orders.append(order)
            order.order_id = f"order-{len(self.submitted_orders)}"
            order.status = OrderStatus.SUBMITTED
            return order

        def cancel_order(self, order_id): pass
        def get_order(self, order_id): pass
        def get_orders(self, status=None, limit=50): pass
        def get_current_price(self, symbol): pass

    def test_buy_market_convenience(self):
        """Test buy_market convenience method."""
        broker = self.MockBroker()
        order = broker.buy_market("AAPL", Decimal("100"))

        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.quantity == Decimal("100")
        assert order.order_type == OrderType.MARKET
        assert order.time_in_force == "day"
        assert len(broker.submitted_orders) == 1

    def test_buy_market_custom_time_in_force(self):
        """Test buy_market with custom time_in_force."""
        broker = self.MockBroker()
        order = broker.buy_market("AAPL", Decimal("100"), time_in_force="gtc")

        assert order.time_in_force == "gtc"

    def test_sell_market_convenience(self):
        """Test sell_market convenience method."""
        broker = self.MockBroker()
        order = broker.sell_market("TSLA", Decimal("50"))

        assert order.symbol == "TSLA"
        assert order.side == OrderSide.SELL
        assert order.quantity == Decimal("50")
        assert order.order_type == OrderType.MARKET

    def test_buy_limit_convenience(self):
        """Test buy_limit convenience method."""
        broker = self.MockBroker()
        order = broker.buy_limit("NVDA", Decimal("25"), Decimal("850.00"))

        assert order.symbol == "NVDA"
        assert order.side == OrderSide.BUY
        assert order.quantity == Decimal("25")
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == Decimal("850.00")

    def test_sell_limit_convenience(self):
        """Test sell_limit convenience method."""
        broker = self.MockBroker()
        order = broker.sell_limit("AMD", Decimal("100"), Decimal("150.00"))

        assert order.symbol == "AMD"
        assert order.side == OrderSide.SELL
        assert order.quantity == Decimal("100")
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == Decimal("150.00")

    def test_buy_limit_with_gtc(self):
        """Test buy_limit with GTC time_in_force."""
        broker = self.MockBroker()
        order = broker.buy_limit(
            "AAPL",
            Decimal("100"),
            Decimal("145.00"),
            time_in_force="gtc"
        )

        assert order.time_in_force == "gtc"
        assert order.limit_price == Decimal("145.00")


@pytest.mark.parametrize("side,expected", [
    (OrderSide.BUY, "buy"),
    (OrderSide.SELL, "sell"),
])
def test_order_side_parametrized(side, expected):
    """Parametrized test for OrderSide values."""
    assert side.value == expected


@pytest.mark.parametrize("order_type,expected", [
    (OrderType.MARKET, "market"),
    (OrderType.LIMIT, "limit"),
    (OrderType.STOP, "stop"),
    (OrderType.STOP_LIMIT, "stop_limit"),
])
def test_order_type_parametrized(order_type, expected):
    """Parametrized test for OrderType values."""
    assert order_type.value == expected


@pytest.mark.parametrize("quantity,price", [
    (Decimal("1"), Decimal("100.00")),
    (Decimal("100"), Decimal("150.50")),
    (Decimal("1000"), Decimal("25.75")),
    (Decimal("0.5"), Decimal("1000.00")),  # Fractional shares
])
def test_order_with_various_quantities(quantity, price):
    """Parametrized test for orders with various quantities."""
    order = BrokerOrder(
        symbol="TEST",
        side=OrderSide.BUY,
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=price
    )

    assert order.quantity == quantity
    assert order.limit_price == price
