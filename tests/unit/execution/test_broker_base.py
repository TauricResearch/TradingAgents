"""Tests for Broker Base Interface module.

Issue #22: [EXEC-21] Broker base interface - abstract broker class
"""

import pytest
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from tradingagents.execution import (
    # Enums
    AssetClass,
    OrderSide,
    OrderType,
    TimeInForce,
    OrderStatus,
    PositionSide,
    # Data Classes
    OrderRequest,
    Order,
    Position,
    AccountInfo,
    Quote,
    AssetInfo,
    # Exceptions
    BrokerError,
    ConnectionError,
    AuthenticationError,
    OrderError,
    InsufficientFundsError,
    InvalidOrderError,
    PositionError,
    RateLimitError,
    # Abstract Base Class
    BrokerBase,
)


# =============================================================================
# Mock Broker Implementation for Testing
# =============================================================================


class MockBroker(BrokerBase):
    """Mock broker implementation for testing abstract base class."""

    def __init__(self, **kwargs):
        super().__init__(
            name="MockBroker",
            supported_asset_classes=[AssetClass.EQUITY, AssetClass.ETF, AssetClass.CRYPTO],
            **kwargs,
        )
        self._orders: Dict[str, Order] = {}
        self._positions: Dict[str, Position] = {}
        self._account: Optional[AccountInfo] = None
        self._quotes: Dict[str, Quote] = {}
        self._assets: Dict[str, AssetInfo] = {}

    async def connect(self) -> bool:
        self._connected = True
        self._account = AccountInfo(
            account_id="TEST123",
            account_type="margin",
            status="active",
            currency="USD",
            cash=Decimal("100000"),
            portfolio_value=Decimal("150000"),
            buying_power=Decimal("200000"),
            equity=Decimal("150000"),
        )
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def is_market_open(self) -> bool:
        return True

    async def get_account(self) -> AccountInfo:
        if not self._connected:
            raise ConnectionError("Not connected")
        return self._account

    async def submit_order(self, request: OrderRequest) -> Order:
        if not self._connected:
            raise ConnectionError("Not connected")

        order = Order(
            broker_order_id=f"ORD-{len(self._orders) + 1}",
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            status=OrderStatus.NEW,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            time_in_force=request.time_in_force,
            created_at=datetime.now(),
            submitted_at=datetime.now(),
        )
        self._orders[order.broker_order_id] = order
        return order

    async def cancel_order(self, order_id: str) -> Order:
        if order_id not in self._orders:
            raise OrderError(f"Order {order_id} not found")
        order = self._orders[order_id]
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = datetime.now()
        return order

    async def replace_order(
        self,
        order_id: str,
        quantity: Optional[Decimal] = None,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
    ) -> Order:
        if order_id not in self._orders:
            raise OrderError(f"Order {order_id} not found")

        old_order = self._orders[order_id]
        old_order.status = OrderStatus.REPLACED

        new_order = Order(
            broker_order_id=f"ORD-{len(self._orders) + 1}",
            client_order_id=old_order.client_order_id,
            symbol=old_order.symbol,
            side=old_order.side,
            quantity=quantity or old_order.quantity,
            order_type=old_order.order_type,
            status=OrderStatus.NEW,
            limit_price=limit_price or old_order.limit_price,
            stop_price=stop_price or old_order.stop_price,
            time_in_force=time_in_force or old_order.time_in_force,
            created_at=datetime.now(),
            submitted_at=datetime.now(),
        )
        self._orders[new_order.broker_order_id] = new_order
        return new_order

    async def get_order(self, order_id: str) -> Order:
        if order_id not in self._orders:
            raise OrderError(f"Order {order_id} not found")
        return self._orders[order_id]

    async def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        limit: int = 100,
        symbols: Optional[List[str]] = None,
    ) -> List[Order]:
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status == status]
        if symbols:
            orders = [o for o in orders if o.symbol in symbols]
        return orders[:limit]

    async def get_positions(self) -> List[Position]:
        return list(self._positions.values())

    async def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    async def get_quote(self, symbol: str) -> Quote:
        if symbol in self._quotes:
            return self._quotes[symbol]
        # Return default quote
        return Quote(
            symbol=symbol,
            bid_price=Decimal("100.00"),
            bid_size=Decimal("100"),
            ask_price=Decimal("100.05"),
            ask_size=Decimal("200"),
            last_price=Decimal("100.02"),
            volume=1000000,
            timestamp=datetime.now(),
        )

    async def get_asset(self, symbol: str) -> AssetInfo:
        if symbol in self._assets:
            return self._assets[symbol]
        # Return default asset
        return AssetInfo(
            symbol=symbol,
            name=f"{symbol} Inc.",
            asset_class=AssetClass.EQUITY,
            tradable=True,
            marginable=True,
            shortable=True,
        )

    # Helper methods for testing
    def add_position(self, position: Position) -> None:
        self._positions[position.symbol] = position

    def add_quote(self, quote: Quote) -> None:
        self._quotes[quote.symbol] = quote

    def add_asset(self, asset: AssetInfo) -> None:
        self._assets[asset.symbol] = asset

    def fill_order(self, order_id: str, avg_price: Decimal) -> Order:
        if order_id in self._orders:
            order = self._orders[order_id]
            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.filled_avg_price = avg_price
            order.filled_at = datetime.now()
        return self._orders.get(order_id)


# =============================================================================
# Enum Tests
# =============================================================================


class TestAssetClass:
    """Tests for AssetClass enum."""

    def test_all_asset_classes(self):
        """Test all asset classes are defined."""
        assert AssetClass.EQUITY.value == "equity"
        assert AssetClass.ETF.value == "etf"
        assert AssetClass.OPTION.value == "option"
        assert AssetClass.FUTURE.value == "future"
        assert AssetClass.CRYPTO.value == "crypto"
        assert AssetClass.FOREX.value == "forex"
        assert AssetClass.BOND.value == "bond"
        assert AssetClass.INDEX.value == "index"


class TestOrderSide:
    """Tests for OrderSide enum."""

    def test_order_sides(self):
        """Test order sides are defined."""
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"


class TestOrderType:
    """Tests for OrderType enum."""

    def test_order_types(self):
        """Test all order types are defined."""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"
        assert OrderType.STOP_LIMIT.value == "stop_limit"
        assert OrderType.TRAILING_STOP.value == "trailing_stop"


class TestTimeInForce:
    """Tests for TimeInForce enum."""

    def test_time_in_force_values(self):
        """Test all time in force values are defined."""
        assert TimeInForce.DAY.value == "day"
        assert TimeInForce.GTC.value == "gtc"
        assert TimeInForce.IOC.value == "ioc"
        assert TimeInForce.FOK.value == "fok"
        assert TimeInForce.OPG.value == "opg"
        assert TimeInForce.CLS.value == "cls"
        assert TimeInForce.GTD.value == "gtd"


class TestOrderStatus:
    """Tests for OrderStatus enum."""

    def test_order_status_values(self):
        """Test all order status values are defined."""
        assert OrderStatus.PENDING_NEW.value == "pending_new"
        assert OrderStatus.NEW.value == "new"
        assert OrderStatus.PARTIALLY_FILLED.value == "partially_filled"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.PENDING_CANCEL.value == "pending_cancel"
        assert OrderStatus.CANCELLED.value == "cancelled"
        assert OrderStatus.REJECTED.value == "rejected"
        assert OrderStatus.EXPIRED.value == "expired"
        assert OrderStatus.REPLACED.value == "replaced"


class TestPositionSide:
    """Tests for PositionSide enum."""

    def test_position_sides(self):
        """Test position sides are defined."""
        assert PositionSide.LONG.value == "long"
        assert PositionSide.SHORT.value == "short"


# =============================================================================
# OrderRequest Tests
# =============================================================================


class TestOrderRequest:
    """Tests for OrderRequest dataclass."""

    def test_create_market_order(self):
        """Test creating a market order."""
        request = OrderRequest.market("AAPL", OrderSide.BUY, 100)

        assert request.symbol == "AAPL"
        assert request.side == OrderSide.BUY
        assert request.quantity == Decimal("100")
        assert request.order_type == OrderType.MARKET
        assert request.time_in_force == TimeInForce.DAY
        assert request.client_order_id is not None

    def test_create_limit_order(self):
        """Test creating a limit order."""
        request = OrderRequest.limit(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            limit_price=150.00,
        )

        assert request.symbol == "AAPL"
        assert request.side == OrderSide.BUY
        assert request.quantity == Decimal("100")
        assert request.order_type == OrderType.LIMIT
        assert request.limit_price == Decimal("150.00")
        assert request.time_in_force == TimeInForce.GTC

    def test_create_stop_order(self):
        """Test creating a stop order."""
        request = OrderRequest.stop(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            stop_price=145.00,
        )

        assert request.order_type == OrderType.STOP
        assert request.stop_price == Decimal("145.00")

    def test_create_stop_limit_order(self):
        """Test creating a stop-limit order."""
        request = OrderRequest.stop_limit(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            stop_price=145.00,
            limit_price=144.50,
        )

        assert request.order_type == OrderType.STOP_LIMIT
        assert request.stop_price == Decimal("145.00")
        assert request.limit_price == Decimal("144.50")

    def test_create_trailing_stop_percent(self):
        """Test creating a trailing stop order with percent."""
        request = OrderRequest.trailing_stop(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            trail_percent=5.0,
        )

        assert request.order_type == OrderType.TRAILING_STOP
        assert request.trail_percent == Decimal("5.0")
        assert request.trail_amount is None

    def test_create_trailing_stop_amount(self):
        """Test creating a trailing stop order with amount."""
        request = OrderRequest.trailing_stop(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            trail_amount=5.00,
        )

        assert request.order_type == OrderType.TRAILING_STOP
        assert request.trail_amount == Decimal("5.00")
        assert request.trail_percent is None

    def test_limit_order_requires_limit_price(self):
        """Test that limit orders require limit price."""
        with pytest.raises(ValueError, match="Limit orders require limit_price"):
            OrderRequest(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
                order_type=OrderType.LIMIT,
            )

    def test_stop_order_requires_stop_price(self):
        """Test that stop orders require stop price."""
        with pytest.raises(ValueError, match="Stop orders require stop_price"):
            OrderRequest(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
                order_type=OrderType.STOP,
            )

    def test_stop_limit_requires_both_prices(self):
        """Test that stop-limit orders require both prices."""
        with pytest.raises(ValueError, match="Stop-limit orders require both"):
            OrderRequest(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
                order_type=OrderType.STOP_LIMIT,
                limit_price=Decimal("150"),
                # Missing stop_price
            )

    def test_trailing_stop_requires_trail_value(self):
        """Test that trailing stop orders require trail value."""
        with pytest.raises(ValueError, match="Trailing stop orders require"):
            OrderRequest(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
                order_type=OrderType.TRAILING_STOP,
            )

    def test_order_with_metadata(self):
        """Test order with custom metadata."""
        request = OrderRequest.market(
            "AAPL",
            OrderSide.BUY,
            100,
            metadata={"strategy": "momentum", "signal_strength": 0.85},
        )

        assert request.metadata["strategy"] == "momentum"
        assert request.metadata["signal_strength"] == 0.85


# =============================================================================
# Order Tests
# =============================================================================


class TestOrder:
    """Tests for Order dataclass."""

    def test_order_is_open(self):
        """Test is_open property."""
        order = Order(
            broker_order_id="ORD-1",
            client_order_id="CLT-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET,
            status=OrderStatus.NEW,
        )
        assert order.is_open is True

        order.status = OrderStatus.FILLED
        assert order.is_open is False

    def test_order_is_filled(self):
        """Test is_filled property."""
        order = Order(
            broker_order_id="ORD-1",
            client_order_id="CLT-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET,
            status=OrderStatus.FILLED,
        )
        assert order.is_filled is True

    def test_order_is_cancelled(self):
        """Test is_cancelled property."""
        order = Order(
            broker_order_id="ORD-1",
            client_order_id="CLT-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET,
            status=OrderStatus.CANCELLED,
        )
        assert order.is_cancelled is True

    def test_remaining_quantity(self):
        """Test remaining_quantity property."""
        order = Order(
            broker_order_id="ORD-1",
            client_order_id="CLT-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET,
            status=OrderStatus.PARTIALLY_FILLED,
            filled_quantity=Decimal("60"),
        )
        assert order.remaining_quantity == Decimal("40")

    def test_fill_percent(self):
        """Test fill_percent property."""
        order = Order(
            broker_order_id="ORD-1",
            client_order_id="CLT-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET,
            status=OrderStatus.PARTIALLY_FILLED,
            filled_quantity=Decimal("60"),
        )
        assert order.fill_percent == 60.0


# =============================================================================
# Position Tests
# =============================================================================


class TestPosition:
    """Tests for Position dataclass."""

    def test_position_long(self):
        """Test long position properties."""
        position = Position(
            symbol="AAPL",
            quantity=Decimal("100"),
            side=PositionSide.LONG,
            avg_entry_price=Decimal("150.00"),
            current_price=Decimal("160.00"),
            market_value=Decimal("16000.00"),
            cost_basis=Decimal("15000.00"),
            unrealized_pnl=Decimal("1000.00"),
            unrealized_pnl_percent=Decimal("6.67"),
        )

        assert position.is_long is True
        assert position.is_short is False
        assert position.abs_quantity == Decimal("100")

    def test_position_short(self):
        """Test short position properties."""
        position = Position(
            symbol="AAPL",
            quantity=Decimal("-100"),
            side=PositionSide.SHORT,
            avg_entry_price=Decimal("150.00"),
            current_price=Decimal("140.00"),
            market_value=Decimal("-14000.00"),
            cost_basis=Decimal("-15000.00"),
            unrealized_pnl=Decimal("1000.00"),
            unrealized_pnl_percent=Decimal("6.67"),
        )

        assert position.is_long is False
        assert position.is_short is True
        assert position.abs_quantity == Decimal("100")


# =============================================================================
# AccountInfo Tests
# =============================================================================


class TestAccountInfo:
    """Tests for AccountInfo dataclass."""

    def test_account_is_active(self):
        """Test is_active property."""
        account = AccountInfo(
            account_id="TEST123",
            account_type="margin",
            status="active",
        )
        assert account.is_active is True

        account.status = "inactive"
        assert account.is_active is False

    def test_account_defaults(self):
        """Test account default values."""
        account = AccountInfo(
            account_id="TEST123",
            account_type="cash",
            status="active",
        )

        assert account.currency == "USD"
        assert account.cash == Decimal("0")
        assert account.portfolio_value == Decimal("0")
        assert account.is_pattern_day_trader is False


# =============================================================================
# Quote Tests
# =============================================================================


class TestQuote:
    """Tests for Quote dataclass."""

    def test_quote_mid_price(self):
        """Test mid_price calculation."""
        quote = Quote(
            symbol="AAPL",
            bid_price=Decimal("100.00"),
            ask_price=Decimal("100.10"),
        )
        assert quote.mid_price == Decimal("100.05")

    def test_quote_mid_price_fallback(self):
        """Test mid_price fallback to last_price."""
        quote = Quote(
            symbol="AAPL",
            last_price=Decimal("100.05"),
        )
        assert quote.mid_price == Decimal("100.05")

    def test_quote_spread(self):
        """Test spread calculation."""
        quote = Quote(
            symbol="AAPL",
            bid_price=Decimal("100.00"),
            ask_price=Decimal("100.10"),
        )
        assert quote.spread == Decimal("0.10")

    def test_quote_spread_percent(self):
        """Test spread_percent calculation."""
        quote = Quote(
            symbol="AAPL",
            bid_price=Decimal("100.00"),
            ask_price=Decimal("100.10"),
        )
        # spread / mid_price * 100 = 0.10 / 100.05 * 100 ≈ 0.0999%
        assert quote.spread_percent is not None
        assert abs(quote.spread_percent - 0.0999) < 0.001


# =============================================================================
# AssetInfo Tests
# =============================================================================


class TestAssetInfo:
    """Tests for AssetInfo dataclass."""

    def test_asset_defaults(self):
        """Test asset default values."""
        asset = AssetInfo(
            symbol="AAPL",
            name="Apple Inc.",
        )

        assert asset.asset_class == AssetClass.EQUITY
        assert asset.tradable is True
        assert asset.marginable is True
        assert asset.shortable is True
        assert asset.fractionable is False


# =============================================================================
# Exception Tests
# =============================================================================


class TestBrokerExceptions:
    """Tests for broker exceptions."""

    def test_broker_error(self):
        """Test BrokerError exception."""
        error = BrokerError("Something went wrong", code="ERR001", details={"key": "value"})

        assert str(error) == "Something went wrong"
        assert error.code == "ERR001"
        assert error.details == {"key": "value"}

    def test_connection_error(self):
        """Test ConnectionError exception."""
        error = ConnectionError("Failed to connect")
        assert isinstance(error, BrokerError)

    def test_authentication_error(self):
        """Test AuthenticationError exception."""
        error = AuthenticationError("Invalid credentials")
        assert isinstance(error, BrokerError)

    def test_order_error(self):
        """Test OrderError exception."""
        error = OrderError("Order failed")
        assert isinstance(error, BrokerError)

    def test_insufficient_funds_error(self):
        """Test InsufficientFundsError exception."""
        error = InsufficientFundsError("Not enough buying power")
        assert isinstance(error, OrderError)

    def test_invalid_order_error(self):
        """Test InvalidOrderError exception."""
        error = InvalidOrderError("Invalid order parameters")
        assert isinstance(error, OrderError)

    def test_position_error(self):
        """Test PositionError exception."""
        error = PositionError("Position not found")
        assert isinstance(error, BrokerError)

    def test_rate_limit_error(self):
        """Test RateLimitError exception."""
        error = RateLimitError("Rate limit exceeded", retry_after=60.0)

        assert isinstance(error, BrokerError)
        assert error.retry_after == 60.0


# =============================================================================
# BrokerBase Tests
# =============================================================================


class TestBrokerBase:
    """Tests for BrokerBase abstract class."""

    @pytest.fixture
    def broker(self):
        """Create a mock broker instance."""
        return MockBroker(paper_trading=True)

    def test_broker_properties(self, broker):
        """Test broker properties."""
        assert broker.name == "MockBroker"
        assert broker.is_paper_trading is True
        assert broker.is_connected is False

    def test_supported_asset_classes(self, broker):
        """Test supported asset classes."""
        assert AssetClass.EQUITY in broker.supported_asset_classes
        assert AssetClass.ETF in broker.supported_asset_classes
        assert AssetClass.CRYPTO in broker.supported_asset_classes
        assert broker.supports_asset_class(AssetClass.EQUITY) is True
        assert broker.supports_asset_class(AssetClass.FOREX) is False

    @pytest.mark.asyncio
    async def test_connect(self, broker):
        """Test connect method."""
        result = await broker.connect()
        assert result is True
        assert broker.is_connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self, broker):
        """Test disconnect method."""
        await broker.connect()
        await broker.disconnect()
        assert broker.is_connected is False

    @pytest.mark.asyncio
    async def test_get_account(self, broker):
        """Test get_account method."""
        await broker.connect()
        account = await broker.get_account()

        assert account.account_id == "TEST123"
        assert account.cash == Decimal("100000")
        assert account.is_active is True

    @pytest.mark.asyncio
    async def test_submit_market_order(self, broker):
        """Test submitting a market order."""
        await broker.connect()

        request = OrderRequest.market("AAPL", OrderSide.BUY, 100)
        order = await broker.submit_order(request)

        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.quantity == Decimal("100")
        assert order.status == OrderStatus.NEW

    @pytest.mark.asyncio
    async def test_submit_limit_order(self, broker):
        """Test submitting a limit order."""
        await broker.connect()

        request = OrderRequest.limit("AAPL", OrderSide.BUY, 100, 150.00)
        order = await broker.submit_order(request)

        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_cancel_order(self, broker):
        """Test cancelling an order."""
        await broker.connect()

        request = OrderRequest.market("AAPL", OrderSide.BUY, 100)
        order = await broker.submit_order(request)

        cancelled = await broker.cancel_order(order.broker_order_id)
        assert cancelled.status == OrderStatus.CANCELLED
        assert cancelled.cancelled_at is not None

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self, broker):
        """Test cancelling a non-existent order."""
        await broker.connect()

        with pytest.raises(OrderError, match="not found"):
            await broker.cancel_order("NONEXISTENT")

    @pytest.mark.asyncio
    async def test_replace_order(self, broker):
        """Test replacing an order."""
        await broker.connect()

        request = OrderRequest.limit("AAPL", OrderSide.BUY, 100, 150.00)
        order = await broker.submit_order(request)

        new_order = await broker.replace_order(
            order.broker_order_id,
            quantity=Decimal("200"),
            limit_price=Decimal("155.00"),
        )

        assert new_order.quantity == Decimal("200")
        assert new_order.limit_price == Decimal("155.00")
        assert new_order.status == OrderStatus.NEW

    @pytest.mark.asyncio
    async def test_get_order(self, broker):
        """Test getting an order."""
        await broker.connect()

        request = OrderRequest.market("AAPL", OrderSide.BUY, 100)
        submitted = await broker.submit_order(request)

        order = await broker.get_order(submitted.broker_order_id)
        assert order.broker_order_id == submitted.broker_order_id

    @pytest.mark.asyncio
    async def test_get_orders_filter_by_status(self, broker):
        """Test getting orders filtered by status."""
        await broker.connect()

        # Submit some orders
        await broker.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, 100))
        order2 = await broker.submit_order(OrderRequest.market("GOOGL", OrderSide.BUY, 50))
        await broker.cancel_order(order2.broker_order_id)

        # Get only NEW orders
        orders = await broker.get_orders(status=OrderStatus.NEW)
        assert len(orders) == 1
        assert orders[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_orders_filter_by_symbols(self, broker):
        """Test getting orders filtered by symbols."""
        await broker.connect()

        await broker.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, 100))
        await broker.submit_order(OrderRequest.market("GOOGL", OrderSide.BUY, 50))
        await broker.submit_order(OrderRequest.market("MSFT", OrderSide.BUY, 75))

        orders = await broker.get_orders(symbols=["AAPL", "MSFT"])
        assert len(orders) == 2
        symbols = {o.symbol for o in orders}
        assert symbols == {"AAPL", "MSFT"}

    @pytest.mark.asyncio
    async def test_cancel_all_orders(self, broker):
        """Test cancelling all orders."""
        await broker.connect()

        await broker.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, 100))
        await broker.submit_order(OrderRequest.market("GOOGL", OrderSide.BUY, 50))
        await broker.submit_order(OrderRequest.market("MSFT", OrderSide.BUY, 75))

        cancelled = await broker.cancel_all_orders()
        assert len(cancelled) == 3

        # All orders should be cancelled
        orders = await broker.get_orders(status=OrderStatus.NEW)
        assert len(orders) == 0

    @pytest.mark.asyncio
    async def test_get_positions(self, broker):
        """Test getting positions."""
        await broker.connect()

        # Add a test position
        broker.add_position(
            Position(
                symbol="AAPL",
                quantity=Decimal("100"),
                side=PositionSide.LONG,
                avg_entry_price=Decimal("150.00"),
                current_price=Decimal("160.00"),
                market_value=Decimal("16000.00"),
                cost_basis=Decimal("15000.00"),
                unrealized_pnl=Decimal("1000.00"),
                unrealized_pnl_percent=Decimal("6.67"),
            )
        )

        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_position(self, broker):
        """Test getting a specific position."""
        await broker.connect()

        broker.add_position(
            Position(
                symbol="AAPL",
                quantity=Decimal("100"),
                side=PositionSide.LONG,
                avg_entry_price=Decimal("150.00"),
                current_price=Decimal("160.00"),
                market_value=Decimal("16000.00"),
                cost_basis=Decimal("15000.00"),
                unrealized_pnl=Decimal("1000.00"),
                unrealized_pnl_percent=Decimal("6.67"),
            )
        )

        position = await broker.get_position("AAPL")
        assert position is not None
        assert position.symbol == "AAPL"

        position = await broker.get_position("NONEXISTENT")
        assert position is None

    @pytest.mark.asyncio
    async def test_close_position(self, broker):
        """Test closing a position."""
        await broker.connect()

        broker.add_position(
            Position(
                symbol="AAPL",
                quantity=Decimal("100"),
                side=PositionSide.LONG,
                avg_entry_price=Decimal("150.00"),
                current_price=Decimal("160.00"),
                market_value=Decimal("16000.00"),
                cost_basis=Decimal("15000.00"),
                unrealized_pnl=Decimal("1000.00"),
                unrealized_pnl_percent=Decimal("6.67"),
            )
        )

        order = await broker.close_position("AAPL")
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.SELL  # Closing long = sell
        assert order.quantity == Decimal("100")

    @pytest.mark.asyncio
    async def test_close_position_partial(self, broker):
        """Test partially closing a position."""
        await broker.connect()

        broker.add_position(
            Position(
                symbol="AAPL",
                quantity=Decimal("100"),
                side=PositionSide.LONG,
                avg_entry_price=Decimal("150.00"),
                current_price=Decimal("160.00"),
                market_value=Decimal("16000.00"),
                cost_basis=Decimal("15000.00"),
                unrealized_pnl=Decimal("1000.00"),
                unrealized_pnl_percent=Decimal("6.67"),
            )
        )

        order = await broker.close_position("AAPL", quantity=Decimal("50"))
        assert order.quantity == Decimal("50")

    @pytest.mark.asyncio
    async def test_close_nonexistent_position(self, broker):
        """Test closing a non-existent position."""
        await broker.connect()

        with pytest.raises(PositionError, match="No position found"):
            await broker.close_position("NONEXISTENT")

    @pytest.mark.asyncio
    async def test_close_short_position(self, broker):
        """Test closing a short position."""
        await broker.connect()

        broker.add_position(
            Position(
                symbol="AAPL",
                quantity=Decimal("-100"),
                side=PositionSide.SHORT,
                avg_entry_price=Decimal("150.00"),
                current_price=Decimal("140.00"),
                market_value=Decimal("-14000.00"),
                cost_basis=Decimal("-15000.00"),
                unrealized_pnl=Decimal("1000.00"),
                unrealized_pnl_percent=Decimal("6.67"),
            )
        )

        order = await broker.close_position("AAPL")
        assert order.side == OrderSide.BUY  # Closing short = buy

    @pytest.mark.asyncio
    async def test_close_all_positions(self, broker):
        """Test closing all positions."""
        await broker.connect()

        broker.add_position(
            Position(
                symbol="AAPL",
                quantity=Decimal("100"),
                side=PositionSide.LONG,
                avg_entry_price=Decimal("150.00"),
                current_price=Decimal("160.00"),
                market_value=Decimal("16000.00"),
                cost_basis=Decimal("15000.00"),
                unrealized_pnl=Decimal("1000.00"),
                unrealized_pnl_percent=Decimal("6.67"),
            )
        )
        broker.add_position(
            Position(
                symbol="GOOGL",
                quantity=Decimal("50"),
                side=PositionSide.LONG,
                avg_entry_price=Decimal("2800.00"),
                current_price=Decimal("2900.00"),
                market_value=Decimal("145000.00"),
                cost_basis=Decimal("140000.00"),
                unrealized_pnl=Decimal("5000.00"),
                unrealized_pnl_percent=Decimal("3.57"),
            )
        )

        orders = await broker.close_all_positions()
        assert len(orders) == 2

    @pytest.mark.asyncio
    async def test_get_quote(self, broker):
        """Test getting a quote."""
        await broker.connect()

        quote = await broker.get_quote("AAPL")
        assert quote.symbol == "AAPL"
        assert quote.bid_price is not None
        assert quote.ask_price is not None

    @pytest.mark.asyncio
    async def test_get_quotes(self, broker):
        """Test getting multiple quotes."""
        await broker.connect()

        quotes = await broker.get_quotes(["AAPL", "GOOGL", "MSFT"])
        assert len(quotes) == 3
        assert "AAPL" in quotes
        assert "GOOGL" in quotes
        assert "MSFT" in quotes

    @pytest.mark.asyncio
    async def test_get_asset(self, broker):
        """Test getting asset information."""
        await broker.connect()

        asset = await broker.get_asset("AAPL")
        assert asset.symbol == "AAPL"
        assert asset.tradable is True

    @pytest.mark.asyncio
    async def test_validate_order_valid(self, broker):
        """Test validating a valid order."""
        await broker.connect()

        request = OrderRequest.market("AAPL", OrderSide.BUY, 100)
        errors = await broker.validate_order(request)
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_validate_order_zero_quantity(self, broker):
        """Test validating order with zero quantity."""
        await broker.connect()

        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("0"),
            order_type=OrderType.MARKET,
        )
        errors = await broker.validate_order(request)
        assert "Quantity must be positive" in errors

    @pytest.mark.asyncio
    async def test_validate_order_non_tradable(self, broker):
        """Test validating order for non-tradable asset."""
        await broker.connect()

        # Add a non-tradable asset
        broker.add_asset(
            AssetInfo(
                symbol="DELISTED",
                name="Delisted Stock",
                tradable=False,
            )
        )

        request = OrderRequest.market("DELISTED", OrderSide.BUY, 100)
        errors = await broker.validate_order(request)
        assert any("not currently tradable" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_limit_order_no_price(self, broker):
        """Test validating limit order without price."""
        await broker.connect()

        # Manually construct invalid request (bypassing __post_init__)
        request = OrderRequest.__new__(OrderRequest)
        request.symbol = "AAPL"
        request.side = OrderSide.BUY
        request.quantity = Decimal("100")
        request.order_type = OrderType.LIMIT
        request.limit_price = None
        request.stop_price = None
        request.time_in_force = TimeInForce.GTC
        request.client_order_id = "test"
        request.extended_hours = False
        request.trail_amount = None
        request.trail_percent = None
        request.take_profit_price = None
        request.stop_loss_price = None
        request.metadata = {}

        errors = await broker.validate_order(request)
        assert any("Limit price must be positive" in e for e in errors)

    def test_broker_repr(self, broker):
        """Test broker string representation."""
        repr_str = repr(broker)
        assert "MockBroker" in repr_str
        assert "paper_trading=True" in repr_str


# =============================================================================
# Integration Tests
# =============================================================================


class TestBrokerWorkflow:
    """Integration tests for complete trading workflows."""

    @pytest.fixture
    def broker(self):
        """Create a mock broker instance."""
        return MockBroker(paper_trading=True)

    @pytest.mark.asyncio
    async def test_full_trade_workflow(self, broker):
        """Test a complete trading workflow."""
        # 1. Connect
        await broker.connect()
        assert broker.is_connected

        # 2. Check account
        account = await broker.get_account()
        assert account.buying_power > 0

        # 3. Get quote
        quote = await broker.get_quote("AAPL")
        assert quote.last_price is not None

        # 4. Submit order
        request = OrderRequest.market("AAPL", OrderSide.BUY, 100)
        order = await broker.submit_order(request)
        assert order.status == OrderStatus.NEW

        # 5. Order gets filled (simulate)
        broker.fill_order(order.broker_order_id, Decimal("150.00"))

        # 6. Check filled order
        filled_order = await broker.get_order(order.broker_order_id)
        assert filled_order.is_filled
        assert filled_order.filled_avg_price == Decimal("150.00")

        # 7. Add position (simulate broker updating positions)
        broker.add_position(
            Position(
                symbol="AAPL",
                quantity=Decimal("100"),
                side=PositionSide.LONG,
                avg_entry_price=Decimal("150.00"),
                current_price=Decimal("155.00"),
                market_value=Decimal("15500.00"),
                cost_basis=Decimal("15000.00"),
                unrealized_pnl=Decimal("500.00"),
                unrealized_pnl_percent=Decimal("3.33"),
            )
        )

        # 8. Check positions
        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"

        # 9. Close position
        close_order = await broker.close_position("AAPL")
        assert close_order.side == OrderSide.SELL
        assert close_order.quantity == Decimal("100")

        # 10. Disconnect
        await broker.disconnect()
        assert not broker.is_connected

    @pytest.mark.asyncio
    async def test_order_modification_workflow(self, broker):
        """Test order modification workflow."""
        await broker.connect()

        # Submit limit order
        request = OrderRequest.limit("AAPL", OrderSide.BUY, 100, 145.00)
        order = await broker.submit_order(request)

        # Modify the order
        new_order = await broker.replace_order(
            order.broker_order_id,
            limit_price=Decimal("147.50"),
        )

        assert new_order.limit_price == Decimal("147.50")

        # Original order should be replaced
        original = await broker.get_order(order.broker_order_id)
        assert original.status == OrderStatus.REPLACED

    @pytest.mark.asyncio
    async def test_risk_management_workflow(self, broker):
        """Test risk management with stop orders."""
        await broker.connect()

        # Submit main order
        buy_request = OrderRequest.market("AAPL", OrderSide.BUY, 100)
        await broker.submit_order(buy_request)

        # Submit stop loss
        stop_request = OrderRequest.stop(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            stop_price=140.00,
        )
        stop_order = await broker.submit_order(stop_request)

        assert stop_order.order_type == OrderType.STOP
        assert stop_order.stop_price == Decimal("140.00")

        # Cancel stop if price moves up
        await broker.cancel_order(stop_order.broker_order_id)

        # Submit new stop at higher price (trailing manually)
        new_stop_request = OrderRequest.stop(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            stop_price=145.00,
        )
        new_stop = await broker.submit_order(new_stop_request)

        assert new_stop.stop_price == Decimal("145.00")
