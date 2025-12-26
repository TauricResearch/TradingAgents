"""Tests for Alpaca Broker module.

Issue #24: [EXEC-23] Alpaca broker - US stocks, ETFs, crypto

These tests use mocks to test the broker without requiring actual
Alpaca API credentials.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import sys

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
    AuthenticationError,
    ConnectionError,
    OrderError,
    InsufficientFundsError,
    InvalidOrderError,
    PositionError,
    RateLimitError,
)


# =============================================================================
# Mock Alpaca SDK
# =============================================================================


class MockAlpacaOrderSide:
    """Mock Alpaca OrderSide enum."""
    BUY = "buy"
    SELL = "sell"


class MockAlpacaOrderType:
    """Mock Alpaca OrderType enum."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class MockAlpacaOrderStatus:
    """Mock Alpaca OrderStatus enum."""
    NEW = "new"
    ACCEPTED = "accepted"
    PENDING_NEW = "pending_new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    REJECTED = "rejected"
    DONE_FOR_DAY = "done_for_day"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    ACCEPTED_FOR_BIDDING = "accepted_for_bidding"
    STOPPED = "stopped"
    SUSPENDED = "suspended"
    CALCULATED = "calculated"


class MockAlpacaTimeInForce:
    """Mock Alpaca TimeInForce enum."""
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    OPG = "opg"
    CLS = "cls"


class MockQueryOrderStatus:
    """Mock Alpaca QueryOrderStatus."""
    OPEN = "open"
    CLOSED = "closed"
    ALL = "all"


class MockAlpacaPositionSide:
    """Mock Alpaca PositionSide."""
    LONG = "long"
    SHORT = "short"


class MockAlpacaAccount:
    """Mock Alpaca account response."""

    def __init__(
        self,
        account_number: str = "TEST123456",
        status: str = "ACTIVE",
        cash: str = "100000.00",
        portfolio_value: str = "150000.00",
        buying_power: str = "200000.00",
        equity: str = "150000.00",
        initial_margin: str = "5000.00",
        regt_buying_power: str = "195000.00",
        daytrade_count: int = 0,
        pattern_day_trader: bool = False,
        account_type: str = "margin",
    ):
        self.account_number = account_number
        self.status = status
        self.cash = cash
        self.portfolio_value = portfolio_value
        self.buying_power = buying_power
        self.equity = equity
        self.initial_margin = initial_margin
        self.regt_buying_power = regt_buying_power
        self.daytrade_count = daytrade_count
        self.pattern_day_trader = pattern_day_trader
        self.account_type = account_type


class MockAlpacaClock:
    """Mock Alpaca clock response."""

    def __init__(self, is_open: bool = True):
        self.is_open = is_open
        self.timestamp = datetime.now(timezone.utc)
        self.next_open = datetime.now(timezone.utc)
        self.next_close = datetime.now(timezone.utc)


class MockAlpacaOrder:
    """Mock Alpaca order response."""

    def __init__(
        self,
        id: str = "order-123",
        client_order_id: Optional[str] = None,
        symbol: str = "AAPL",
        side: str = "buy",
        qty: str = "100",
        order_type: str = "market",
        status: str = "new",
        limit_price: Optional[str] = None,
        stop_price: Optional[str] = None,
        time_in_force: str = "day",
        filled_qty: str = "0",
        filled_avg_price: Optional[str] = None,
    ):
        self.id = id
        self.client_order_id = client_order_id
        self.symbol = symbol
        self.side = MagicMock()
        self.side.__eq__ = lambda s, other: side == other.value if hasattr(other, 'value') else side == other
        # For comparison, mock the value attribute
        if side == "buy":
            self.side = type('MockSide', (), {'value': 'buy', '__eq__': lambda s, o: o == MockAlpacaOrderSide.BUY or getattr(o, 'value', o) == 'buy'})()
        else:
            self.side = type('MockSide', (), {'value': 'sell', '__eq__': lambda s, o: o == MockAlpacaOrderSide.SELL or getattr(o, 'value', o) == 'sell'})()
        self.qty = qty
        self.order_type = type('MockOrderType', (), {'value': order_type})()
        self.status = type('MockStatus', (), {'value': status})()
        self.limit_price = limit_price
        self.stop_price = stop_price
        self.time_in_force = type('MockTIF', (), {'value': time_in_force})()
        self.filled_qty = filled_qty
        self.filled_avg_price = filled_avg_price
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.submitted_at = datetime.now(timezone.utc)
        self.filled_at = None
        self.expired_at = None
        self.canceled_at = None


class MockAlpacaPosition:
    """Mock Alpaca position response."""

    def __init__(
        self,
        symbol: str = "AAPL",
        qty: str = "100",
        avg_entry_price: str = "150.00",
        current_price: str = "160.00",
        market_value: str = "16000.00",
        cost_basis: str = "15000.00",
        unrealized_pl: str = "1000.00",
        unrealized_plpc: str = "0.0667",
        asset_class: str = "us_equity",
    ):
        self.symbol = symbol
        self.qty = qty
        self.avg_entry_price = avg_entry_price
        self.current_price = current_price
        self.market_value = market_value
        self.cost_basis = cost_basis
        self.unrealized_pl = unrealized_pl
        self.unrealized_plpc = unrealized_plpc
        self.asset_class = asset_class


class MockAlpacaAsset:
    """Mock Alpaca asset response."""

    def __init__(
        self,
        symbol: str = "AAPL",
        name: str = "Apple Inc.",
        asset_class: str = "us_equity",
        exchange: str = "NASDAQ",
        tradable: bool = True,
        shortable: bool = True,
        marginable: bool = True,
        fractionable: bool = True,
        easy_to_borrow: bool = True,
    ):
        self.symbol = symbol
        self.name = name
        self.asset_class = asset_class
        self.exchange = exchange
        self.tradable = tradable
        self.shortable = shortable
        self.marginable = marginable
        self.fractionable = fractionable
        self.easy_to_borrow = easy_to_borrow


class MockAlpacaQuote:
    """Mock Alpaca quote response."""

    def __init__(
        self,
        symbol: str = "AAPL",
        bid_price: float = 159.95,
        ask_price: float = 160.05,
        bid_size: int = 100,
        ask_size: int = 100,
    ):
        self.symbol = symbol
        self.bid_price = bid_price
        self.ask_price = ask_price
        self.bid_size = bid_size
        self.ask_size = ask_size
        self.timestamp = datetime.now(timezone.utc)


class MockTradingClient:
    """Mock Alpaca TradingClient."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self._orders: Dict[str, MockAlpacaOrder] = {}
        self._order_counter = 0

    def get_account(self) -> MockAlpacaAccount:
        return MockAlpacaAccount()

    def get_clock(self) -> MockAlpacaClock:
        return MockAlpacaClock()

    def submit_order(self, request: Any) -> MockAlpacaOrder:
        self._order_counter += 1
        order_id = f"order-{self._order_counter}"
        order = MockAlpacaOrder(
            id=order_id,
            symbol=request.symbol,
            qty=str(request.qty),
            side="buy" if str(request.side).lower() == "buy" else "sell",
            order_type=getattr(request, 'order_type', 'market') or 'market',
            limit_price=str(getattr(request, 'limit_price', None)) if getattr(request, 'limit_price', None) else None,
            stop_price=str(getattr(request, 'stop_price', None)) if getattr(request, 'stop_price', None) else None,
            client_order_id=getattr(request, 'client_order_id', None),
        )
        self._orders[order_id] = order
        return order

    def cancel_order_by_id(self, order_id: str) -> None:
        if order_id in self._orders:
            self._orders[order_id].status = type('MockStatus', (), {'value': 'canceled'})()

    def get_order_by_id(self, order_id: str) -> MockAlpacaOrder:
        if order_id in self._orders:
            return self._orders[order_id]
        raise Exception(f"Order {order_id} not found")

    def replace_order_by_id(self, order_id: str, order_data: Any) -> MockAlpacaOrder:
        self._order_counter += 1
        new_order_id = f"order-{self._order_counter}"
        old_order = self._orders.get(order_id)
        if not old_order:
            raise Exception(f"Order {order_id} not found")

        new_order = MockAlpacaOrder(
            id=new_order_id,
            symbol=old_order.symbol,
            qty=str(order_data.qty) if order_data.qty else old_order.qty,
            side=old_order.side.value,
            limit_price=str(order_data.limit_price) if order_data.limit_price else old_order.limit_price,
            stop_price=str(order_data.stop_price) if order_data.stop_price else old_order.stop_price,
        )
        self._orders[new_order_id] = new_order
        return new_order

    def get_orders(self, request: Any) -> List[MockAlpacaOrder]:
        return list(self._orders.values())

    def get_all_positions(self) -> List[MockAlpacaPosition]:
        return [MockAlpacaPosition()]

    def get_open_position(self, symbol: str) -> MockAlpacaPosition:
        return MockAlpacaPosition(symbol=symbol)

    def get_asset(self, symbol: str) -> MockAlpacaAsset:
        return MockAlpacaAsset(symbol=symbol)


class MockStockHistoricalDataClient:
    """Mock Alpaca StockHistoricalDataClient."""

    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key

    def get_stock_latest_quote(self, request: Any) -> Dict[str, MockAlpacaQuote]:
        symbols = request.symbol_or_symbols
        return {symbol: MockAlpacaQuote(symbol=symbol) for symbol in symbols}


class MockCryptoHistoricalDataClient:
    """Mock Alpaca CryptoHistoricalDataClient."""

    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key

    def get_crypto_latest_quote(self, request: Any) -> Dict[str, MockAlpacaQuote]:
        symbols = request.symbol_or_symbols
        return {symbol: MockAlpacaQuote(symbol=symbol) for symbol in symbols}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_alpaca_module():
    """Create mock alpaca module."""
    # Create mock module structure
    mock_trading = MagicMock()
    mock_trading.client.TradingClient = MockTradingClient
    mock_trading.requests.MarketOrderRequest = MagicMock
    mock_trading.requests.LimitOrderRequest = MagicMock
    mock_trading.requests.StopOrderRequest = MagicMock
    mock_trading.requests.StopLimitOrderRequest = MagicMock
    mock_trading.requests.TrailingStopOrderRequest = MagicMock
    mock_trading.requests.ReplaceOrderRequest = MagicMock
    mock_trading.requests.GetOrdersRequest = MagicMock
    mock_trading.enums.OrderSide = MockAlpacaOrderSide
    mock_trading.enums.OrderType = MockAlpacaOrderType
    mock_trading.enums.OrderStatus = MockAlpacaOrderStatus
    mock_trading.enums.TimeInForce = MockAlpacaTimeInForce
    mock_trading.enums.QueryOrderStatus = MockQueryOrderStatus
    mock_trading.enums.PositionSide = MockAlpacaPositionSide

    mock_data = MagicMock()
    mock_data.historical.StockHistoricalDataClient = MockStockHistoricalDataClient
    mock_data.historical.CryptoHistoricalDataClient = MockCryptoHistoricalDataClient
    mock_data.requests.StockLatestQuoteRequest = MagicMock
    mock_data.requests.CryptoLatestQuoteRequest = MagicMock
    mock_data.live.StockDataStream = MagicMock
    mock_data.live.CryptoDataStream = MagicMock

    return mock_trading, mock_data


# =============================================================================
# AlpacaBroker Tests - Initialization
# =============================================================================


class TestAlpacaBrokerInit:
    """Tests for AlpacaBroker initialization."""

    def test_init_default(self):
        """Test default initialization."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker()

        assert broker.name == "Alpaca"
        assert broker.is_paper_trading is True
        assert AssetClass.EQUITY in broker.supported_asset_classes
        assert AssetClass.ETF in broker.supported_asset_classes
        assert AssetClass.CRYPTO in broker.supported_asset_classes

    def test_init_with_credentials(self):
        """Test initialization with credentials."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker(
            api_key="test-api-key",
            api_secret="test-api-secret",
            paper_trading=True,
        )

        assert broker.api_key == "test****-key"  # Masked

    def test_init_live_trading(self):
        """Test initialization for live trading."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker(
            api_key="test-api-key",
            api_secret="test-api-secret",
            paper_trading=False,
        )

        assert broker.is_paper_trading is False
        assert "paper" not in broker.base_url

    def test_init_paper_trading(self):
        """Test initialization for paper trading."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker(
            api_key="test-api-key",
            api_secret="test-api-secret",
            paper_trading=True,
        )

        assert broker.is_paper_trading is True
        assert "paper" in broker.base_url


# =============================================================================
# AlpacaBroker Tests - Connection (with mocks)
# =============================================================================


class TestAlpacaBrokerConnection:
    """Tests for connection management."""

    @pytest.mark.asyncio
    async def test_connect_without_credentials(self):
        """Test connect fails without credentials."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker, ALPACA_AVAILABLE

        if not ALPACA_AVAILABLE:
            pytest.skip("alpaca-py not installed")

        broker = AlpacaBroker(api_key="", api_secret="")

        with pytest.raises(AuthenticationError, match="credentials not provided"):
            await broker.connect()

    @pytest.mark.asyncio
    async def test_connect_without_sdk(self):
        """Test connect fails gracefully without SDK."""
        from tradingagents.execution import alpaca_broker

        # Save original value
        original_available = alpaca_broker.ALPACA_AVAILABLE

        try:
            # Mock SDK not available
            alpaca_broker.ALPACA_AVAILABLE = False

            broker = alpaca_broker.AlpacaBroker(
                api_key="test-key",
                api_secret="test-secret",
            )

            with pytest.raises(BrokerError, match="alpaca-py is not installed"):
                await broker.connect()

        finally:
            # Restore original value
            alpaca_broker.ALPACA_AVAILABLE = original_available

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test disconnect."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker()
        broker._connected = True

        await broker.disconnect()

        assert broker.is_connected is False


# =============================================================================
# AlpacaBroker Tests - Order Mapping
# =============================================================================


class TestAlpacaBrokerOrderMapping:
    """Tests for order type/side/status mapping."""

    def test_map_order_side_buy(self):
        """Test mapping buy order side."""
        from tradingagents.execution import alpaca_broker

        if not alpaca_broker.ALPACA_AVAILABLE:
            pytest.skip("alpaca-py not installed")

        broker = alpaca_broker.AlpacaBroker()
        result = broker._map_order_side(OrderSide.BUY)

        # Check it maps correctly (exact check depends on SDK)
        assert result is not None

    def test_map_time_in_force(self):
        """Test mapping time in force."""
        from tradingagents.execution import alpaca_broker

        if not alpaca_broker.ALPACA_AVAILABLE:
            pytest.skip("alpaca-py not installed")

        broker = alpaca_broker.AlpacaBroker()

        for tif in TimeInForce:
            result = broker._map_time_in_force(tif)
            assert result is not None


# =============================================================================
# AlpacaBroker Tests - Order Requests (structure tests)
# =============================================================================


class TestAlpacaBrokerOrderRequests:
    """Tests for order request building."""

    def test_market_order_request(self):
        """Test market order request."""
        request = OrderRequest.market("AAPL", OrderSide.BUY, 100)

        assert request.symbol == "AAPL"
        assert request.side == OrderSide.BUY
        assert request.quantity == Decimal("100")
        assert request.order_type == OrderType.MARKET

    def test_limit_order_request(self):
        """Test limit order request."""
        request = OrderRequest.limit(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            limit_price=Decimal("150.00"),
        )

        assert request.symbol == "AAPL"
        assert request.order_type == OrderType.LIMIT
        assert request.limit_price == Decimal("150.00")

    def test_stop_order_request(self):
        """Test stop order request."""
        request = OrderRequest.stop(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            stop_price=Decimal("145.00"),
        )

        assert request.order_type == OrderType.STOP
        assert request.stop_price == Decimal("145.00")

    def test_stop_limit_order_request(self):
        """Test stop-limit order request."""
        request = OrderRequest.stop_limit(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            stop_price=Decimal("145.00"),
            limit_price=Decimal("144.50"),
        )

        assert request.order_type == OrderType.STOP_LIMIT
        assert request.stop_price == Decimal("145.00")
        assert request.limit_price == Decimal("144.50")

    def test_trailing_stop_order_request(self):
        """Test trailing stop order request."""
        request = OrderRequest.trailing_stop(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            trail_percent=Decimal("2.0"),
        )

        assert request.order_type == OrderType.TRAILING_STOP
        assert request.trail_percent == Decimal("2.0")


# =============================================================================
# AlpacaBroker Tests - With Mocked SDK
# =============================================================================


class TestAlpacaBrokerWithMockedSDK:
    """Tests using mocked Alpaca SDK."""

    async def _create_connected_broker(self):
        """Create a broker with mocked SDK and connect it."""
        from tradingagents.execution import alpaca_broker

        # Set up broker
        broker = alpaca_broker.AlpacaBroker(
            api_key="test-key",
            api_secret="test-secret",
            paper_trading=True,
        )

        # Mock the SDK connection
        broker._trading_client = MockTradingClient(
            api_key="test-key",
            secret_key="test-secret",
            paper=True,
        )
        broker._stock_data_client = MockStockHistoricalDataClient(
            api_key="test-key",
            secret_key="test-secret",
        )
        broker._crypto_data_client = MockCryptoHistoricalDataClient(
            api_key="test-key",
            secret_key="test-secret",
        )
        broker._connected = True

        return broker

    @pytest.mark.asyncio
    async def test_get_account(self):
        """Test getting account info."""
        broker = await self._create_connected_broker()

        account = await broker.get_account()

        assert isinstance(account, AccountInfo)
        assert account.account_id == "TEST123456"
        assert account.status == "ACTIVE"
        assert account.cash == Decimal("100000.00")

    @pytest.mark.asyncio
    async def test_is_market_open(self):
        """Test checking market status."""
        broker = await self._create_connected_broker()

        is_open = await broker.is_market_open()

        assert is_open is True

    @pytest.mark.asyncio
    async def test_submit_market_order(self):
        """Test submitting market order."""
        from tradingagents.execution import alpaca_broker

        if not alpaca_broker.ALPACA_AVAILABLE:
            pytest.skip("alpaca-py not installed")

        broker = await self._create_connected_broker()
        request = OrderRequest.market("AAPL", OrderSide.BUY, 100)

        order = await broker.submit_order(request)

        assert order is not None
        assert order.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_positions(self):
        """Test getting positions."""
        broker = await self._create_connected_broker()

        positions = await broker.get_positions()

        assert len(positions) >= 1
        assert positions[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_position(self):
        """Test getting specific position."""
        broker = await self._create_connected_broker()

        position = await broker.get_position("AAPL")

        assert position is not None
        assert position.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_quote_stock(self):
        """Test getting stock quote."""
        from tradingagents.execution import alpaca_broker

        if not alpaca_broker.ALPACA_AVAILABLE:
            pytest.skip("alpaca-py not installed")

        broker = await self._create_connected_broker()

        quote = await broker.get_quote("AAPL")

        assert quote.symbol == "AAPL"
        assert quote.bid_price is not None
        assert quote.ask_price is not None

    @pytest.mark.asyncio
    async def test_get_quote_crypto(self):
        """Test getting crypto quote."""
        from tradingagents.execution import alpaca_broker

        if not alpaca_broker.ALPACA_AVAILABLE:
            pytest.skip("alpaca-py not installed")

        broker = await self._create_connected_broker()

        quote = await broker.get_quote("BTCUSD")

        assert quote.symbol == "BTCUSD"

    @pytest.mark.asyncio
    async def test_get_asset(self):
        """Test getting asset info."""
        broker = await self._create_connected_broker()

        asset = await broker.get_asset("AAPL")

        assert asset.symbol == "AAPL"
        assert asset.name == "Apple Inc."
        assert asset.tradable is True


# =============================================================================
# AlpacaBroker Tests - Error Handling
# =============================================================================


class TestAlpacaBrokerErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_requires_connection(self):
        """Test operations fail without connection."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker(api_key="test", api_secret="test")

        with pytest.raises(ConnectionError, match="Not connected"):
            await broker.get_account()

    @pytest.mark.asyncio
    async def test_invalid_limit_order_without_price(self):
        """Test limit order without price fails."""
        from tradingagents.execution import alpaca_broker

        if not alpaca_broker.ALPACA_AVAILABLE:
            pytest.skip("alpaca-py not installed")

        broker = alpaca_broker.AlpacaBroker(
            api_key="test-key",
            api_secret="test-secret",
        )
        broker._trading_client = MockTradingClient(
            api_key="test", secret_key="test"
        )
        broker._connected = True

        # Create limit order request without limit price
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            # Missing limit_price
        )

        with pytest.raises(InvalidOrderError, match="Limit price required"):
            await broker.submit_order(request)

    @pytest.mark.asyncio
    async def test_invalid_stop_order_without_price(self):
        """Test stop order without price fails."""
        from tradingagents.execution import alpaca_broker

        if not alpaca_broker.ALPACA_AVAILABLE:
            pytest.skip("alpaca-py not installed")

        broker = alpaca_broker.AlpacaBroker(
            api_key="test-key",
            api_secret="test-secret",
        )
        broker._trading_client = MockTradingClient(
            api_key="test", secret_key="test"
        )
        broker._connected = True

        # Create stop order without stop price
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=Decimal("100"),
            order_type=OrderType.STOP,
            time_in_force=TimeInForce.DAY,
            # Missing stop_price
        )

        with pytest.raises(InvalidOrderError, match="Stop price required"):
            await broker.submit_order(request)


# =============================================================================
# AlpacaBroker Tests - Asset Class Support
# =============================================================================


class TestAlpacaBrokerAssetClasses:
    """Tests for asset class support."""

    def test_supports_equity(self):
        """Test broker supports equity."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker()

        assert broker.supports_asset_class(AssetClass.EQUITY) is True

    def test_supports_etf(self):
        """Test broker supports ETF."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker()

        assert broker.supports_asset_class(AssetClass.ETF) is True

    def test_supports_crypto(self):
        """Test broker supports crypto."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker()

        assert broker.supports_asset_class(AssetClass.CRYPTO) is True

    def test_does_not_support_futures(self):
        """Test broker does not support futures."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker()

        assert broker.supports_asset_class(AssetClass.FUTURE) is False

    def test_does_not_support_options(self):
        """Test broker does not support options."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker()

        assert broker.supports_asset_class(AssetClass.OPTION) is False


# =============================================================================
# AlpacaBroker Tests - API Key Masking
# =============================================================================


class TestAlpacaBrokerSecurity:
    """Tests for security features."""

    def test_api_key_masked(self):
        """Test API key is masked in property."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker(
            api_key="PKEXAMPLEAPIKEY12345",
            api_secret="supersecretkey",
        )

        # Key should be masked
        assert "****" in broker.api_key
        assert "EXAMPLE" not in broker.api_key

    def test_short_api_key_fully_masked(self):
        """Test short API key is fully masked."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker(
            api_key="short",
            api_secret="test",
        )

        # Short keys should be fully masked
        assert broker.api_key == "****"


# =============================================================================
# AlpacaBroker Tests - URL Configuration
# =============================================================================


class TestAlpacaBrokerURLs:
    """Tests for URL configuration."""

    def test_paper_url(self):
        """Test paper trading URL."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker(paper_trading=True)

        assert "paper" in broker.base_url

    def test_live_url(self):
        """Test live trading URL."""
        from tradingagents.execution.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker(paper_trading=False)

        assert "paper" not in broker.base_url
        assert "api.alpaca.markets" in broker.base_url


# =============================================================================
# Integration with BrokerRouter
# =============================================================================


class TestAlpacaBrokerRouterIntegration:
    """Tests for AlpacaBroker integration with BrokerRouter."""

    def test_register_with_router(self):
        """Test registering AlpacaBroker with router."""
        from tradingagents.execution import AlpacaBroker, BrokerRouter

        router = BrokerRouter()
        broker = AlpacaBroker()

        router.register(broker)

        assert "Alpaca" in router.registered_brokers
        assert AssetClass.EQUITY in router.supported_asset_classes
        assert AssetClass.CRYPTO in router.supported_asset_classes

    def test_route_to_alpaca(self):
        """Test routing routes to Alpaca for supported assets."""
        from tradingagents.execution import AlpacaBroker, BrokerRouter

        router = BrokerRouter()
        broker = AlpacaBroker()
        router.register(broker)

        routed_broker, decision = router.route("AAPL")

        assert routed_broker.name == "Alpaca"
        assert decision.asset_class == AssetClass.EQUITY

    def test_route_crypto_to_alpaca(self):
        """Test crypto routing goes to Alpaca."""
        from tradingagents.execution import AlpacaBroker, BrokerRouter

        router = BrokerRouter()
        broker = AlpacaBroker()
        router.register(broker)

        routed_broker, decision = router.route("BTCUSD")

        assert routed_broker.name == "Alpaca"
        assert decision.asset_class == AssetClass.CRYPTO
