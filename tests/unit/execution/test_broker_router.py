"""Tests for Broker Router module.

Issue #23: [EXEC-22] Broker router - route by asset class
"""

import pytest
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

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
    OrderError,
    PositionError,
    # Base Class
    BrokerBase,
    # Router
    BrokerRouter,
    BrokerRegistration,
    RoutingDecision,
    SymbolClassifier,
    RoutingError,
    NoBrokerError,
    BrokerNotFoundError,
    DuplicateBrokerError,
)


# =============================================================================
# Mock Broker for Testing
# =============================================================================


class MockBroker(BrokerBase):
    """Mock broker for testing router functionality."""

    def __init__(
        self,
        name: str,
        asset_classes: List[AssetClass],
        paper_trading: bool = True,
    ):
        super().__init__(
            name=name,
            supported_asset_classes=asset_classes,
            paper_trading=paper_trading,
        )
        self._orders: Dict[str, Order] = {}
        self._positions: Dict[str, Position] = {}
        self._order_counter = 0

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def is_market_open(self) -> bool:
        return True

    async def get_account(self) -> AccountInfo:
        return AccountInfo(
            account_id=f"{self._name}_account",
            account_type="margin",
            status="active",
            cash=Decimal("100000"),
            portfolio_value=Decimal("150000"),
            buying_power=Decimal("200000"),
            equity=Decimal("150000"),
        )

    async def submit_order(self, request: OrderRequest) -> Order:
        self._order_counter += 1
        order = Order(
            broker_order_id=f"{self._name}-ORD-{self._order_counter}",
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
        )
        self._orders[order.broker_order_id] = order
        return order

    async def cancel_order(self, order_id: str) -> Order:
        if order_id not in self._orders:
            raise OrderError(f"Order {order_id} not found")
        order = self._orders[order_id]
        order.status = OrderStatus.CANCELLED
        return order

    async def replace_order(
        self,
        order_id: str,
        quantity: Optional[Decimal] = None,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
    ) -> Order:
        old_order = self._orders.get(order_id)
        if not old_order:
            raise OrderError(f"Order {order_id} not found")

        self._order_counter += 1
        new_order = Order(
            broker_order_id=f"{self._name}-ORD-{self._order_counter}",
            client_order_id=old_order.client_order_id,
            symbol=old_order.symbol,
            side=old_order.side,
            quantity=quantity or old_order.quantity,
            order_type=old_order.order_type,
            status=OrderStatus.NEW,
            limit_price=limit_price or old_order.limit_price,
            stop_price=stop_price or old_order.stop_price,
            time_in_force=time_in_force or old_order.time_in_force,
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
        return Quote(
            symbol=symbol,
            bid_price=Decimal("100.00"),
            ask_price=Decimal("100.05"),
            last_price=Decimal("100.02"),
            volume=1000000,
        )

    async def get_asset(self, symbol: str) -> AssetInfo:
        return AssetInfo(
            symbol=symbol,
            name=f"{symbol} Asset",
            tradable=True,
        )

    def add_position(self, position: Position) -> None:
        """Helper to add test positions."""
        self._positions[position.symbol] = position


# =============================================================================
# SymbolClassifier Tests
# =============================================================================


class TestSymbolClassifier:
    """Tests for SymbolClassifier."""

    def test_classify_equity(self):
        """Test equity classification."""
        classifier = SymbolClassifier()

        assert classifier.classify("AAPL") == AssetClass.EQUITY
        assert classifier.classify("MSFT") == AssetClass.EQUITY
        assert classifier.classify("GOOGL") == AssetClass.EQUITY

    def test_classify_etf(self):
        """Test ETF classification."""
        classifier = SymbolClassifier()

        assert classifier.classify("SPY") == AssetClass.ETF
        assert classifier.classify("QQQ") == AssetClass.ETF
        assert classifier.classify("VTI") == AssetClass.ETF

    def test_classify_crypto(self):
        """Test crypto classification."""
        classifier = SymbolClassifier()

        assert classifier.classify("BTCUSD") == AssetClass.CRYPTO
        assert classifier.classify("ETHUSD") == AssetClass.CRYPTO
        assert classifier.classify("BTC") == AssetClass.CRYPTO

    def test_classify_future(self):
        """Test futures classification."""
        classifier = SymbolClassifier()

        assert classifier.classify("ESZ24") == AssetClass.FUTURE  # S&P 500 Dec 2024
        assert classifier.classify("CLF25") == AssetClass.FUTURE  # Crude Oil Jan 2025
        assert classifier.classify("GCG24") == AssetClass.FUTURE  # Gold Feb 2024

    def test_custom_mapping(self):
        """Test custom symbol mapping."""
        classifier = SymbolClassifier()

        # Add custom mapping
        classifier.add_mapping("CUSTOM", AssetClass.BOND)

        assert classifier.classify("CUSTOM") == AssetClass.BOND

    def test_custom_mapping_overrides_default(self):
        """Test that custom mappings override defaults."""
        classifier = SymbolClassifier()

        # SPY is normally an ETF
        assert classifier.classify("SPY") == AssetClass.ETF

        # Override with custom mapping
        classifier.add_mapping("SPY", AssetClass.EQUITY)
        classifier.clear_cache()  # Clear cache to pick up new mapping

        assert classifier.classify("SPY") == AssetClass.EQUITY

    def test_cache(self):
        """Test classification caching."""
        classifier = SymbolClassifier()

        # First call should classify
        result1 = classifier.classify("AAPL")

        # Second call should use cache
        result2 = classifier.classify("AAPL")

        assert result1 == result2 == AssetClass.EQUITY

    def test_clear_cache(self):
        """Test clearing classification cache."""
        classifier = SymbolClassifier()

        classifier.classify("AAPL")  # Populate cache

        classifier.clear_cache()

        # Should still work after cache clear
        assert classifier.classify("AAPL") == AssetClass.EQUITY


# =============================================================================
# BrokerRegistration Tests
# =============================================================================


class TestBrokerRegistration:
    """Tests for BrokerRegistration dataclass."""

    def test_create_registration(self):
        """Test creating a broker registration."""
        broker = MockBroker("TestBroker", [AssetClass.EQUITY])

        reg = BrokerRegistration(
            broker=broker,
            asset_classes={AssetClass.EQUITY, AssetClass.ETF},
            priority=10,
            is_primary=True,
        )

        assert reg.broker == broker
        assert AssetClass.EQUITY in reg.asset_classes
        assert reg.priority == 10
        assert reg.is_primary is True
        assert reg.enabled is True

    def test_default_values(self):
        """Test default registration values."""
        broker = MockBroker("TestBroker", [AssetClass.EQUITY])

        reg = BrokerRegistration(
            broker=broker,
            asset_classes={AssetClass.EQUITY},
        )

        assert reg.priority == 0
        assert reg.is_primary is False
        assert reg.enabled is True
        assert reg.registered_at is not None


# =============================================================================
# RoutingDecision Tests
# =============================================================================


class TestRoutingDecision:
    """Tests for RoutingDecision dataclass."""

    def test_create_decision(self):
        """Test creating a routing decision."""
        decision = RoutingDecision(
            symbol="AAPL",
            asset_class=AssetClass.EQUITY,
            broker_name="Alpaca",
            reason="Primary broker for equity",
            alternatives=["IBKR"],
        )

        assert decision.symbol == "AAPL"
        assert decision.asset_class == AssetClass.EQUITY
        assert decision.broker_name == "Alpaca"
        assert "IBKR" in decision.alternatives


# =============================================================================
# BrokerRouter Tests - Registration
# =============================================================================


class TestBrokerRouterRegistration:
    """Tests for broker registration."""

    def test_register_broker(self):
        """Test registering a broker."""
        router = BrokerRouter()
        broker = MockBroker("Alpaca", [AssetClass.EQUITY, AssetClass.ETF])

        router.register(broker)

        assert "Alpaca" in router.registered_brokers
        assert AssetClass.EQUITY in router.supported_asset_classes

    def test_register_with_specific_classes(self):
        """Test registering with specific asset classes."""
        router = BrokerRouter()
        broker = MockBroker("Alpaca", [AssetClass.EQUITY, AssetClass.ETF, AssetClass.CRYPTO])

        # Only register for equity
        router.register(broker, asset_classes=[AssetClass.EQUITY])

        assert AssetClass.EQUITY in router.supported_asset_classes
        # ETF and CRYPTO not registered even though broker supports them
        assert AssetClass.CRYPTO not in router.supported_asset_classes

    def test_register_duplicate_raises(self):
        """Test registering duplicate broker raises error."""
        router = BrokerRouter()
        broker = MockBroker("Alpaca", [AssetClass.EQUITY])

        router.register(broker)

        with pytest.raises(DuplicateBrokerError, match="already registered"):
            router.register(broker)

    def test_unregister_broker(self):
        """Test unregistering a broker."""
        router = BrokerRouter()
        broker = MockBroker("Alpaca", [AssetClass.EQUITY])

        router.register(broker)
        router.unregister("Alpaca")

        assert "Alpaca" not in router.registered_brokers

    def test_unregister_nonexistent_raises(self):
        """Test unregistering non-existent broker raises error."""
        router = BrokerRouter()

        with pytest.raises(BrokerNotFoundError, match="not registered"):
            router.unregister("NonExistent")

    def test_get_broker(self):
        """Test getting a broker by name."""
        router = BrokerRouter()
        broker = MockBroker("Alpaca", [AssetClass.EQUITY])

        router.register(broker)

        result = router.get_broker("Alpaca")
        assert result == broker

    def test_get_broker_not_found(self):
        """Test getting non-existent broker raises error."""
        router = BrokerRouter()

        with pytest.raises(BrokerNotFoundError):
            router.get_broker("NonExistent")


# =============================================================================
# BrokerRouter Tests - Routing
# =============================================================================


class TestBrokerRouterRouting:
    """Tests for order routing."""

    @pytest.fixture
    def router_with_brokers(self):
        """Create a router with multiple brokers."""
        router = BrokerRouter()

        equity_broker = MockBroker("EquityBroker", [AssetClass.EQUITY, AssetClass.ETF])
        crypto_broker = MockBroker("CryptoBroker", [AssetClass.CRYPTO])
        futures_broker = MockBroker("FuturesBroker", [AssetClass.FUTURE, AssetClass.OPTION])

        router.register(equity_broker, [AssetClass.EQUITY, AssetClass.ETF])
        router.register(crypto_broker, [AssetClass.CRYPTO])
        router.register(futures_broker, [AssetClass.FUTURE, AssetClass.OPTION])

        return router

    def test_route_equity(self, router_with_brokers):
        """Test routing equity symbol."""
        broker, decision = router_with_brokers.route("AAPL")

        assert broker.name == "EquityBroker"
        assert decision.asset_class == AssetClass.EQUITY

    def test_route_etf(self, router_with_brokers):
        """Test routing ETF symbol."""
        broker, decision = router_with_brokers.route("SPY")

        assert broker.name == "EquityBroker"
        assert decision.asset_class == AssetClass.ETF

    def test_route_crypto(self, router_with_brokers):
        """Test routing crypto symbol."""
        broker, decision = router_with_brokers.route("BTCUSD")

        assert broker.name == "CryptoBroker"
        assert decision.asset_class == AssetClass.CRYPTO

    def test_route_futures(self, router_with_brokers):
        """Test routing futures symbol."""
        broker, decision = router_with_brokers.route("ESZ24")

        assert broker.name == "FuturesBroker"
        assert decision.asset_class == AssetClass.FUTURE

    def test_route_no_broker_raises(self):
        """Test routing when no broker available."""
        router = BrokerRouter()

        with pytest.raises(NoBrokerError, match="No broker available"):
            router.route("AAPL")

    def test_fallback_broker(self):
        """Test fallback broker usage."""
        router = BrokerRouter()
        equity_broker = MockBroker("EquityBroker", [AssetClass.EQUITY])

        router.register(equity_broker)
        router.set_fallback("EquityBroker")

        # Route an unknown asset class (FOREX) - should use fallback
        router.add_symbol_mapping("EURUSD", AssetClass.FOREX)
        broker, decision = router.route("EURUSD")

        assert broker.name == "EquityBroker"
        assert "Fallback" in decision.reason

    def test_disabled_broker_skipped(self, router_with_brokers):
        """Test that disabled brokers are skipped."""
        router_with_brokers.disable_broker("EquityBroker")

        with pytest.raises(NoBrokerError):
            router_with_brokers.route("AAPL")

    def test_enable_broker(self, router_with_brokers):
        """Test enabling a broker."""
        router_with_brokers.disable_broker("EquityBroker")
        router_with_brokers.enable_broker("EquityBroker")

        broker, _ = router_with_brokers.route("AAPL")
        assert broker.name == "EquityBroker"

    def test_priority_routing(self):
        """Test priority-based broker selection."""
        router = BrokerRouter()

        low_priority = MockBroker("LowPriority", [AssetClass.EQUITY])
        high_priority = MockBroker("HighPriority", [AssetClass.EQUITY])

        router.register(low_priority, priority=1)
        router.register(high_priority, priority=10)

        broker, _ = router.route("AAPL")
        assert broker.name == "HighPriority"

    def test_primary_broker_preference(self):
        """Test primary broker is preferred."""
        router = BrokerRouter()

        secondary = MockBroker("Secondary", [AssetClass.EQUITY])
        primary = MockBroker("Primary", [AssetClass.EQUITY])

        router.register(secondary, priority=10)
        router.register(primary, priority=1, primary=True)

        broker, _ = router.route("AAPL")
        assert broker.name == "Primary"

    def test_routing_history(self, router_with_brokers):
        """Test routing history tracking."""
        router_with_brokers.route("AAPL")
        router_with_brokers.route("SPY")
        router_with_brokers.route("BTCUSD")

        history = router_with_brokers.get_routing_history()

        assert len(history) == 3
        # Most recent first
        assert history[0].symbol == "BTCUSD"
        assert history[1].symbol == "SPY"
        assert history[2].symbol == "AAPL"

    def test_routing_history_filter(self, router_with_brokers):
        """Test filtering routing history by symbol."""
        router_with_brokers.route("AAPL")
        router_with_brokers.route("SPY")
        router_with_brokers.route("AAPL")

        history = router_with_brokers.get_routing_history(symbol="AAPL")

        assert len(history) == 2
        assert all(d.symbol == "AAPL" for d in history)


# =============================================================================
# BrokerRouter Tests - Order Management
# =============================================================================


class TestBrokerRouterOrders:
    """Tests for order management through router."""

    async def _create_connected_router(self):
        """Create a connected router."""
        router = BrokerRouter()

        equity_broker = MockBroker("EquityBroker", [AssetClass.EQUITY, AssetClass.ETF])
        crypto_broker = MockBroker("CryptoBroker", [AssetClass.CRYPTO])

        router.register(equity_broker)
        router.register(crypto_broker)

        await router.connect_all()
        return router

    @pytest.mark.asyncio
    async def test_submit_order_auto_route(self):
        """Test submitting order with auto-routing."""
        router = await self._create_connected_router()
        request = OrderRequest.market("AAPL", OrderSide.BUY, 100)

        order = await router.submit_order(request)

        assert order.symbol == "AAPL"
        assert "EquityBroker" in order.broker_order_id

    @pytest.mark.asyncio
    async def test_submit_order_specific_broker(self):
        """Test submitting order to specific broker."""
        router = await self._create_connected_router()
        request = OrderRequest.market("AAPL", OrderSide.BUY, 100)

        order = await router.submit_order(request, broker_name="EquityBroker")

        assert "EquityBroker" in order.broker_order_id

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """Test cancelling an order."""
        router = await self._create_connected_router()
        request = OrderRequest.market("AAPL", OrderSide.BUY, 100)
        order = await router.submit_order(request)

        cancelled = await router.cancel_order(
            order.broker_order_id,
            broker_name="EquityBroker"
        )

        assert cancelled.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_get_orders_single_broker(self):
        """Test getting orders from single broker."""
        router = await self._create_connected_router()
        await router.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, 100))
        await router.submit_order(OrderRequest.market("BTCUSD", OrderSide.BUY, 1))

        orders = await router.get_orders(broker_name="EquityBroker")

        assert "EquityBroker" in orders
        assert len(orders["EquityBroker"]) == 1

    @pytest.mark.asyncio
    async def test_get_orders_all_brokers(self):
        """Test getting orders from all brokers."""
        router = await self._create_connected_router()
        await router.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, 100))
        await router.submit_order(OrderRequest.market("BTCUSD", OrderSide.BUY, 1))

        orders = await router.get_orders()

        assert len(orders) == 2  # Two brokers
        assert "EquityBroker" in orders
        assert "CryptoBroker" in orders

    @pytest.mark.asyncio
    async def test_cancel_all_orders(self):
        """Test cancelling all orders."""
        router = await self._create_connected_router()
        await router.submit_order(OrderRequest.market("AAPL", OrderSide.BUY, 100))
        await router.submit_order(OrderRequest.market("MSFT", OrderSide.BUY, 50))

        cancelled = await router.cancel_all_orders()

        assert "EquityBroker" in cancelled
        assert len(cancelled["EquityBroker"]) == 2


# =============================================================================
# BrokerRouter Tests - Position Management
# =============================================================================


class TestBrokerRouterPositions:
    """Tests for position management through router."""

    async def _create_router_with_positions(self):
        """Create router with positions."""
        router = BrokerRouter()

        equity_broker = MockBroker("EquityBroker", [AssetClass.EQUITY])
        crypto_broker = MockBroker("CryptoBroker", [AssetClass.CRYPTO])

        router.register(equity_broker)
        router.register(crypto_broker)

        await router.connect_all()

        # Add some positions
        equity_broker.add_position(Position(
            symbol="AAPL",
            quantity=Decimal("100"),
            side=PositionSide.LONG,
            avg_entry_price=Decimal("150"),
            current_price=Decimal("160"),
            market_value=Decimal("16000"),
            cost_basis=Decimal("15000"),
            unrealized_pnl=Decimal("1000"),
            unrealized_pnl_percent=Decimal("6.67"),
        ))

        crypto_broker.add_position(Position(
            symbol="BTCUSD",
            quantity=Decimal("1"),
            side=PositionSide.LONG,
            avg_entry_price=Decimal("40000"),
            current_price=Decimal("45000"),
            market_value=Decimal("45000"),
            cost_basis=Decimal("40000"),
            unrealized_pnl=Decimal("5000"),
            unrealized_pnl_percent=Decimal("12.5"),
        ))

        return router

    @pytest.mark.asyncio
    async def test_get_positions_all(self):
        """Test getting positions from all brokers."""
        router = await self._create_router_with_positions()
        positions = await router.get_positions()

        assert len(positions) == 2
        assert "EquityBroker" in positions
        assert "CryptoBroker" in positions

    @pytest.mark.asyncio
    async def test_get_all_positions(self):
        """Test getting aggregated positions."""
        router = await self._create_router_with_positions()
        positions = await router.get_all_positions()

        assert len(positions) == 2
        symbols = {p[1].symbol for p in positions}
        assert "AAPL" in symbols
        assert "BTCUSD" in symbols

    @pytest.mark.asyncio
    async def test_get_position(self):
        """Test getting specific position."""
        router = await self._create_router_with_positions()
        result = await router.get_position("AAPL")

        assert result is not None
        broker_name, position = result
        assert broker_name == "EquityBroker"
        assert position.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_position_not_found(self):
        """Test getting non-existent position."""
        router = await self._create_router_with_positions()
        result = await router.get_position("NONEXISTENT")
        assert result is None

    @pytest.mark.asyncio
    async def test_close_position(self):
        """Test closing a position."""
        router = await self._create_router_with_positions()
        order = await router.close_position("AAPL")

        assert order.symbol == "AAPL"
        assert order.side == OrderSide.SELL
        assert order.quantity == Decimal("100")

    @pytest.mark.asyncio
    async def test_close_position_not_found(self):
        """Test closing non-existent position."""
        router = await self._create_router_with_positions()
        with pytest.raises(PositionError, match="No position found"):
            await router.close_position("NONEXISTENT")


# =============================================================================
# BrokerRouter Tests - Account Management
# =============================================================================


class TestBrokerRouterAccounts:
    """Tests for account management through router."""

    async def _create_connected_router(self):
        """Create connected router."""
        router = BrokerRouter()

        broker1 = MockBroker("Broker1", [AssetClass.EQUITY])
        broker2 = MockBroker("Broker2", [AssetClass.CRYPTO])

        router.register(broker1)
        router.register(broker2)

        await router.connect_all()
        return router

    @pytest.mark.asyncio
    async def test_get_accounts(self):
        """Test getting all accounts."""
        router = await self._create_connected_router()
        accounts = await router.get_accounts()

        assert len(accounts) == 2
        assert "Broker1" in accounts
        assert "Broker2" in accounts

    @pytest.mark.asyncio
    async def test_get_total_equity(self):
        """Test getting total equity."""
        router = await self._create_connected_router()
        equity = await router.get_total_equity()

        # Each mock broker has 150000 equity
        assert equity == Decimal("300000")

    @pytest.mark.asyncio
    async def test_get_total_buying_power(self):
        """Test getting total buying power."""
        router = await self._create_connected_router()
        power = await router.get_total_buying_power()

        # Each mock broker has 200000 buying power
        assert power == Decimal("400000")


# =============================================================================
# BrokerRouter Tests - Market Data
# =============================================================================


class TestBrokerRouterMarketData:
    """Tests for market data through router."""

    async def _create_connected_router(self):
        """Create connected router."""
        router = BrokerRouter()

        equity_broker = MockBroker("EquityBroker", [AssetClass.EQUITY])
        crypto_broker = MockBroker("CryptoBroker", [AssetClass.CRYPTO])

        router.register(equity_broker)
        router.register(crypto_broker)

        await router.connect_all()
        return router

    @pytest.mark.asyncio
    async def test_get_quote(self):
        """Test getting a quote."""
        router = await self._create_connected_router()
        quote = await router.get_quote("AAPL")

        assert quote.symbol == "AAPL"
        assert quote.bid_price is not None

    @pytest.mark.asyncio
    async def test_get_quotes(self):
        """Test getting multiple quotes."""
        router = await self._create_connected_router()
        quotes = await router.get_quotes(["AAPL", "BTCUSD"])

        assert len(quotes) == 2
        assert "AAPL" in quotes
        assert "BTCUSD" in quotes

    @pytest.mark.asyncio
    async def test_get_asset(self):
        """Test getting asset info."""
        router = await self._create_connected_router()
        asset = await router.get_asset("AAPL")

        assert asset.symbol == "AAPL"


# =============================================================================
# BrokerRouter Tests - Connection Management
# =============================================================================


class TestBrokerRouterConnection:
    """Tests for connection management."""

    @pytest.mark.asyncio
    async def test_connect_all(self):
        """Test connecting all brokers."""
        router = BrokerRouter()

        broker1 = MockBroker("Broker1", [AssetClass.EQUITY])
        broker2 = MockBroker("Broker2", [AssetClass.CRYPTO])

        router.register(broker1)
        router.register(broker2)

        results = await router.connect_all()

        assert results["Broker1"] is True
        assert results["Broker2"] is True
        assert broker1.is_connected
        assert broker2.is_connected

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        """Test disconnecting all brokers."""
        router = BrokerRouter()

        broker = MockBroker("Broker", [AssetClass.EQUITY])
        router.register(broker)

        await router.connect_all()
        await router.disconnect_all()

        assert not broker.is_connected

    @pytest.mark.asyncio
    async def test_is_market_open(self):
        """Test checking market status."""
        router = BrokerRouter()

        broker = MockBroker("Broker", [AssetClass.EQUITY])
        router.register(broker)
        await router.connect_all()

        is_open = await router.is_market_open()
        assert is_open is True


# =============================================================================
# BrokerRouter Tests - Status
# =============================================================================


class TestBrokerRouterStatus:
    """Tests for status reporting."""

    def test_get_broker_status(self):
        """Test getting broker status."""
        router = BrokerRouter()

        broker = MockBroker("TestBroker", [AssetClass.EQUITY, AssetClass.ETF])
        router.register(broker, priority=5, primary=True)

        status = router.get_broker_status()

        assert "TestBroker" in status
        broker_status = status["TestBroker"]
        assert broker_status["connected"] is False
        assert broker_status["enabled"] is True
        assert broker_status["priority"] == 5
        assert broker_status["is_primary"] is True
        assert "equity" in broker_status["asset_classes"]

    def test_repr(self):
        """Test string representation."""
        router = BrokerRouter()

        broker1 = MockBroker("Broker1", [AssetClass.EQUITY])
        broker2 = MockBroker("Broker2", [AssetClass.CRYPTO])

        router.register(broker1)
        router.register(broker2)

        repr_str = repr(router)
        assert "BrokerRouter" in repr_str
        assert "Broker1" in repr_str
        assert "Broker2" in repr_str


# =============================================================================
# Router Exception Tests
# =============================================================================


class TestRouterExceptions:
    """Tests for router exceptions."""

    def test_routing_error(self):
        """Test RoutingError exception."""
        error = RoutingError("Routing failed")
        assert isinstance(error, BrokerError)

    def test_no_broker_error(self):
        """Test NoBrokerError exception."""
        error = NoBrokerError("No broker for asset class")
        assert isinstance(error, RoutingError)

    def test_broker_not_found_error(self):
        """Test BrokerNotFoundError exception."""
        error = BrokerNotFoundError("Broker not found")
        assert isinstance(error, RoutingError)

    def test_duplicate_broker_error(self):
        """Test DuplicateBrokerError exception."""
        error = DuplicateBrokerError("Broker already registered")
        assert isinstance(error, RoutingError)
