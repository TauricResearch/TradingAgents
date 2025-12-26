"""Tests for IBKR Broker module.

Issue #25: [EXEC-24] IBKR broker - futures, ASX equities

These tests use mocks to test the broker without requiring actual
IBKR connection or ib_insync SDK.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
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
    AuthenticationError,
    ConnectionError,
    OrderError,
    InsufficientFundsError,
    InvalidOrderError,
    PositionError,
    # IBKR
    IBKRBroker,
    IB_INSYNC_AVAILABLE,
    FUTURES_SPECS,
)


# =============================================================================
# Mock IB_insync classes
# =============================================================================


class MockContract:
    """Mock IBKR Contract."""

    def __init__(
        self,
        symbol: str = "AAPL",
        secType: str = "STK",
        exchange: str = "SMART",
        currency: str = "USD",
    ):
        self.symbol = symbol
        self.secType = secType
        self.exchange = exchange
        self.currency = currency
        self.localSymbol = symbol


class MockOrderStatus:
    """Mock IBKR OrderStatus."""

    def __init__(
        self,
        status: str = "Submitted",
        filled: float = 0,
        avgFillPrice: float = 0,
    ):
        self.status = status
        self.filled = filled
        self.avgFillPrice = avgFillPrice


class MockOrder:
    """Mock IBKR Order."""

    def __init__(
        self,
        orderId: int = 1,
        action: str = "BUY",
        totalQuantity: float = 100,
        orderType: str = "MKT",
        lmtPrice: float = 0,
        auxPrice: float = 0,
        tif: str = "DAY",
    ):
        self.orderId = orderId
        self.action = action
        self.totalQuantity = totalQuantity
        self.orderType = orderType
        self.lmtPrice = lmtPrice
        self.auxPrice = auxPrice
        self.tif = tif


class MockTrade:
    """Mock IBKR Trade."""

    def __init__(
        self,
        order: MockOrder = None,
        contract: MockContract = None,
        orderStatus: MockOrderStatus = None,
    ):
        self.order = order or MockOrder()
        self.contract = contract or MockContract()
        self.orderStatus = orderStatus or MockOrderStatus()


class MockPortfolioItem:
    """Mock IBKR PortfolioItem."""

    def __init__(
        self,
        contract: MockContract = None,
        position: float = 100,
        marketPrice: float = 160.0,
        marketValue: float = 16000.0,
        averageCost: float = 150.0,
        unrealizedPNL: float = 1000.0,
    ):
        self.contract = contract or MockContract()
        self.position = position
        self.marketPrice = marketPrice
        self.marketValue = marketValue
        self.averageCost = averageCost
        self.unrealizedPNL = unrealizedPNL


class MockAccountValue:
    """Mock IBKR AccountValue."""

    def __init__(
        self,
        tag: str = "TotalCashValue",
        value: str = "100000",
        currency: str = "USD",
    ):
        self.tag = tag
        self.value = value
        self.currency = currency


class MockTicker:
    """Mock IBKR Ticker."""

    def __init__(
        self,
        bid: float = 159.95,
        ask: float = 160.05,
        last: float = 160.0,
        bidSize: int = 100,
        askSize: int = 100,
        volume: int = 1000000,
    ):
        self.bid = bid
        self.ask = ask
        self.last = last
        self.bidSize = bidSize
        self.askSize = askSize
        self.volume = volume


class MockIB:
    """Mock IB class."""

    def __init__(self):
        self._connected = False
        self._orders: Dict[int, MockTrade] = {}
        self._order_counter = 0
        self._portfolio: List[MockPortfolioItem] = []
        self._account_values: List[MockAccountValue] = []

    async def connectAsync(self, host: str, port: int, clientId: int) -> None:
        self._connected = True

    def isConnected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        self._connected = False

    def managedAccounts(self) -> List[str]:
        return ["DU1234567"]

    def accountValues(self) -> List[MockAccountValue]:
        return self._account_values or [
            MockAccountValue("TotalCashValue", "100000"),
            MockAccountValue("BuyingPower", "200000"),
            MockAccountValue("NetLiquidation", "150000"),
            MockAccountValue("MaintMarginReq", "5000"),
            MockAccountValue("AvailableFunds", "195000"),
            MockAccountValue("AccountType", "individual"),
        ]

    def portfolio(self) -> List[MockPortfolioItem]:
        return self._portfolio or [
            MockPortfolioItem(
                contract=MockContract("AAPL", "STK"),
                position=100,
            ),
        ]

    async def qualifyContractsAsync(self, contract: MockContract) -> List[MockContract]:
        return [contract]

    def placeOrder(self, contract: MockContract, order: Any) -> MockTrade:
        self._order_counter += 1
        mock_order = MockOrder(
            orderId=self._order_counter,
            action=order.action if hasattr(order, 'action') else "BUY",
            totalQuantity=order.totalQuantity if hasattr(order, 'totalQuantity') else 100,
        )
        trade = MockTrade(order=mock_order, contract=contract)
        self._orders[self._order_counter] = trade
        return trade

    def cancelOrder(self, order: MockOrder) -> None:
        if order.orderId in self._orders:
            self._orders[order.orderId].orderStatus.status = "Cancelled"

    def reqMktData(self, contract: MockContract, *args) -> MockTicker:
        return MockTicker()

    def add_position(self, item: MockPortfolioItem) -> None:
        """Helper to add test positions."""
        self._portfolio.append(item)


# =============================================================================
# IBKRBroker Tests - Initialization
# =============================================================================


class TestIBKRBrokerInit:
    """Tests for IBKRBroker initialization."""

    def test_init_default(self):
        """Test default initialization."""
        broker = IBKRBroker()

        assert broker.name == "IBKR"
        assert broker.is_paper_trading is True
        assert broker.host == "127.0.0.1"
        assert broker.port == 7497  # Paper trading port
        assert AssetClass.FUTURE in broker.supported_asset_classes
        assert AssetClass.EQUITY in broker.supported_asset_classes

    def test_init_with_config(self):
        """Test initialization with custom config."""
        broker = IBKRBroker(
            host="192.168.1.100",
            port=7496,
            client_id=5,
            paper_trading=False,
        )

        assert broker.host == "192.168.1.100"
        assert broker.port == 7496
        assert broker.client_id == 5
        assert broker.is_paper_trading is False

    def test_init_live_trading(self):
        """Test initialization for live trading."""
        broker = IBKRBroker(paper_trading=False)

        assert broker.is_paper_trading is False
        assert broker.port == 7496  # Live port


# =============================================================================
# IBKRBroker Tests - Connection
# =============================================================================


class TestIBKRBrokerConnection:
    """Tests for connection management."""

    @pytest.mark.asyncio
    async def test_connect_without_sdk(self):
        """Test connect fails gracefully without SDK."""
        from tradingagents.execution import ibkr_broker

        # Save original value
        original_available = ibkr_broker.IB_INSYNC_AVAILABLE

        try:
            # Mock SDK not available
            ibkr_broker.IB_INSYNC_AVAILABLE = False

            broker = ibkr_broker.IBKRBroker()

            with pytest.raises(BrokerError, match="ib_insync is not installed"):
                await broker.connect()

        finally:
            # Restore original value
            ibkr_broker.IB_INSYNC_AVAILABLE = original_available

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test disconnect."""
        broker = IBKRBroker()
        broker._connected = True

        await broker.disconnect()

        assert broker.is_connected is False


# =============================================================================
# IBKRBroker Tests - With Mocked SDK
# =============================================================================


class TestIBKRBrokerWithMockedSDK:
    """Tests using mocked ib_insync SDK."""

    async def _create_connected_broker(self):
        """Create a broker with mocked SDK and connect it."""
        broker = IBKRBroker(
            host="127.0.0.1",
            port=7497,
            client_id=1,
            paper_trading=True,
        )

        # Mock the IB connection
        broker._ib = MockIB()
        broker._ib._connected = True
        broker._connected = True

        return broker

    @pytest.mark.asyncio
    async def test_get_account(self):
        """Test getting account info."""
        broker = await self._create_connected_broker()

        account = await broker.get_account()

        assert isinstance(account, AccountInfo)
        assert account.account_id == "DU1234567"
        assert account.cash == Decimal("100000")

    @pytest.mark.asyncio
    async def test_is_market_open(self):
        """Test checking market status."""
        broker = await self._create_connected_broker()

        is_open = await broker.is_market_open()

        assert is_open is True

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
    async def test_get_position_not_found(self):
        """Test getting non-existent position."""
        broker = await self._create_connected_broker()

        position = await broker.get_position("NONEXISTENT")

        assert position is None

    @pytest.mark.asyncio
    async def test_get_quote(self):
        """Test getting quote."""
        from tradingagents.execution import ibkr_broker

        if not ibkr_broker.IB_INSYNC_AVAILABLE:
            pytest.skip("ib_insync not installed")

        broker = await self._create_connected_broker()

        quote = await broker.get_quote("AAPL")

        assert quote.symbol == "AAPL"
        assert quote.bid_price is not None
        assert quote.ask_price is not None


# =============================================================================
# IBKRBroker Tests - Order Validation
# =============================================================================


class TestIBKRBrokerOrderValidation:
    """Tests for order validation."""

    @pytest.mark.asyncio
    async def test_requires_connection(self):
        """Test operations fail without connection."""
        broker = IBKRBroker()

        with pytest.raises(ConnectionError, match="Not connected"):
            await broker.get_account()


# =============================================================================
# IBKRBroker Tests - Contract Creation
# =============================================================================


class TestIBKRBrokerContractCreation:
    """Tests for contract creation."""

    def test_create_contract_stock(self):
        """Test creating stock contract."""
        from tradingagents.execution import ibkr_broker

        if not ibkr_broker.IB_INSYNC_AVAILABLE:
            pytest.skip("ib_insync not installed")

        broker = IBKRBroker()
        contract = broker._create_contract("AAPL")

        assert contract is not None

    def test_create_contract_futures(self):
        """Test creating futures contract."""
        from tradingagents.execution import ibkr_broker

        if not ibkr_broker.IB_INSYNC_AVAILABLE:
            pytest.skip("ib_insync not installed")

        broker = IBKRBroker()
        contract = broker._create_contract("ES")  # E-mini S&P

        assert contract is not None

    def test_create_contract_asx(self):
        """Test creating ASX stock contract."""
        from tradingagents.execution import ibkr_broker

        if not ibkr_broker.IB_INSYNC_AVAILABLE:
            pytest.skip("ib_insync not installed")

        broker = IBKRBroker()
        contract = broker._create_contract("BHP.AX")  # BHP on ASX

        assert contract is not None


# =============================================================================
# IBKRBroker Tests - Asset Class Support
# =============================================================================


class TestIBKRBrokerAssetClasses:
    """Tests for asset class support."""

    def test_supports_equity(self):
        """Test broker supports equity."""
        broker = IBKRBroker()

        assert broker.supports_asset_class(AssetClass.EQUITY) is True

    def test_supports_futures(self):
        """Test broker supports futures."""
        broker = IBKRBroker()

        assert broker.supports_asset_class(AssetClass.FUTURE) is True

    def test_supports_options(self):
        """Test broker supports options."""
        broker = IBKRBroker()

        assert broker.supports_asset_class(AssetClass.OPTION) is True

    def test_supports_forex(self):
        """Test broker supports forex."""
        broker = IBKRBroker()

        assert broker.supports_asset_class(AssetClass.FOREX) is True

    def test_does_not_support_crypto(self):
        """Test broker does not support crypto."""
        broker = IBKRBroker()

        assert broker.supports_asset_class(AssetClass.CRYPTO) is False


# =============================================================================
# IBKRBroker Tests - Futures Specs
# =============================================================================


class TestFuturesSpecs:
    """Tests for futures specifications."""

    def test_es_futures_spec(self):
        """Test E-mini S&P 500 futures spec."""
        assert "ES" in FUTURES_SPECS
        assert FUTURES_SPECS["ES"]["exchange"] == "CME"
        assert FUTURES_SPECS["ES"]["multiplier"] == 50

    def test_nq_futures_spec(self):
        """Test E-mini NASDAQ futures spec."""
        assert "NQ" in FUTURES_SPECS
        assert FUTURES_SPECS["NQ"]["exchange"] == "CME"
        assert FUTURES_SPECS["NQ"]["multiplier"] == 20

    def test_cl_futures_spec(self):
        """Test Crude Oil futures spec."""
        assert "CL" in FUTURES_SPECS
        assert FUTURES_SPECS["CL"]["exchange"] == "NYMEX"
        assert FUTURES_SPECS["CL"]["multiplier"] == 1000

    def test_gc_futures_spec(self):
        """Test Gold futures spec."""
        assert "GC" in FUTURES_SPECS
        assert FUTURES_SPECS["GC"]["exchange"] == "COMEX"
        assert FUTURES_SPECS["GC"]["multiplier"] == 100


# =============================================================================
# IBKRBroker Tests - Status Mapping
# =============================================================================


class TestIBKRBrokerStatusMapping:
    """Tests for status mapping."""

    def test_map_submitted_status(self):
        """Test mapping Submitted status."""
        broker = IBKRBroker()

        status = broker._map_ibkr_status("Submitted")

        assert status == OrderStatus.NEW

    def test_map_filled_status(self):
        """Test mapping Filled status."""
        broker = IBKRBroker()

        status = broker._map_ibkr_status("Filled")

        assert status == OrderStatus.FILLED

    def test_map_cancelled_status(self):
        """Test mapping Cancelled status."""
        broker = IBKRBroker()

        status = broker._map_ibkr_status("Cancelled")

        assert status == OrderStatus.CANCELLED

    def test_map_pending_status(self):
        """Test mapping pending statuses."""
        broker = IBKRBroker()

        # PendingSubmit and PreSubmitted map to PENDING_NEW
        assert broker._map_ibkr_status("PendingSubmit") == OrderStatus.PENDING_NEW
        assert broker._map_ibkr_status("PreSubmitted") == OrderStatus.PENDING_NEW
        # PendingCancel maps to PENDING_CANCEL
        assert broker._map_ibkr_status("PendingCancel") == OrderStatus.PENDING_CANCEL


# =============================================================================
# IBKRBroker Tests - Time In Force Mapping
# =============================================================================


class TestIBKRBrokerTIFMapping:
    """Tests for time in force mapping."""

    def test_map_day_tif(self):
        """Test mapping DAY time in force."""
        broker = IBKRBroker()

        tif = broker._map_time_in_force(TimeInForce.DAY)

        assert tif == "DAY"

    def test_map_gtc_tif(self):
        """Test mapping GTC time in force."""
        broker = IBKRBroker()

        tif = broker._map_time_in_force(TimeInForce.GTC)

        assert tif == "GTC"

    def test_map_ioc_tif(self):
        """Test mapping IOC time in force."""
        broker = IBKRBroker()

        tif = broker._map_time_in_force(TimeInForce.IOC)

        assert tif == "IOC"


# =============================================================================
# IBKRBroker Tests - Order Side Mapping
# =============================================================================


class TestIBKRBrokerSideMapping:
    """Tests for order side mapping."""

    def test_map_buy_side(self):
        """Test mapping BUY side."""
        broker = IBKRBroker()

        side = broker._map_order_side(OrderSide.BUY)

        assert side == "BUY"

    def test_map_sell_side(self):
        """Test mapping SELL side."""
        broker = IBKRBroker()

        side = broker._map_order_side(OrderSide.SELL)

        assert side == "SELL"


# =============================================================================
# IBKRBroker Tests - Router Integration
# =============================================================================


class TestIBKRBrokerRouterIntegration:
    """Tests for IBKRBroker integration with BrokerRouter."""

    def test_register_with_router(self):
        """Test registering IBKRBroker with router."""
        from tradingagents.execution import IBKRBroker, BrokerRouter

        router = BrokerRouter()
        broker = IBKRBroker()

        router.register(broker)

        assert "IBKR" in router.registered_brokers
        assert AssetClass.FUTURE in router.supported_asset_classes
        assert AssetClass.OPTION in router.supported_asset_classes

    def test_route_futures_to_ibkr(self):
        """Test futures routing goes to IBKR."""
        from tradingagents.execution import IBKRBroker, BrokerRouter

        router = BrokerRouter()
        broker = IBKRBroker()
        router.register(broker)

        # ES is a known futures symbol
        routed_broker, decision = router.route("ESZ24")

        assert routed_broker.name == "IBKR"
        assert decision.asset_class == AssetClass.FUTURE


# =============================================================================
# IBKRBroker Tests - URL Configuration
# =============================================================================


class TestIBKRBrokerPorts:
    """Tests for port configuration."""

    def test_paper_port(self):
        """Test paper trading port."""
        broker = IBKRBroker(paper_trading=True)

        assert broker.port == 7497

    def test_live_port(self):
        """Test live trading port."""
        broker = IBKRBroker(paper_trading=False)

        assert broker.port == 7496

    def test_custom_port(self):
        """Test custom port."""
        broker = IBKRBroker(port=4002)

        assert broker.port == 4002
