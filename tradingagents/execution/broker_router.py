"""Broker Router for routing orders by asset class.

This module provides a router that directs orders to the appropriate broker
based on the asset class being traded. This enables multi-broker setups
where different brokers handle different asset classes.

Issue #23: [EXEC-22] Broker router - route by asset class

Example:
    >>> from tradingagents.execution import BrokerRouter, AssetClass
    >>>
    >>> router = BrokerRouter()
    >>> router.register(alpaca_broker, [AssetClass.EQUITY, AssetClass.CRYPTO])
    >>> router.register(ibkr_broker, [AssetClass.FUTURE, AssetClass.OPTION])
    >>>
    >>> # Orders automatically routed to correct broker
    >>> await router.submit_order(order_request)  # Routes based on symbol
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import asyncio

from .broker_base import (
    AssetClass,
    AssetInfo,
    BrokerBase,
    BrokerError,
    Order,
    OrderRequest,
    OrderStatus,
    OrderSide,
    Position,
    Quote,
    AccountInfo,
    TimeInForce,
    PositionError,
    ConnectionError as BrokerConnectionError,
)


class RoutingError(BrokerError):
    """Error in broker routing."""
    pass


class NoBrokerError(RoutingError):
    """No broker available for the requested asset class."""
    pass


class BrokerNotFoundError(RoutingError):
    """Specified broker not found."""
    pass


class DuplicateBrokerError(RoutingError):
    """Broker already registered."""
    pass


@dataclass
class BrokerRegistration:
    """Registration info for a broker.

    Attributes:
        broker: The broker instance
        asset_classes: Asset classes this broker handles
        priority: Priority for routing (higher = preferred)
        is_primary: Whether this is the primary broker for its classes
        enabled: Whether this broker is currently enabled
        registered_at: When the broker was registered
    """
    broker: BrokerBase
    asset_classes: Set[AssetClass]
    priority: int = 0
    is_primary: bool = False
    enabled: bool = True
    registered_at: datetime = field(default_factory=datetime.now)


@dataclass
class RoutingDecision:
    """Record of a routing decision.

    Attributes:
        symbol: Symbol being routed
        asset_class: Detected asset class
        broker_name: Name of selected broker
        reason: Reason for the routing decision
        alternatives: Alternative brokers that could handle this
        timestamp: When decision was made
    """
    symbol: str
    asset_class: AssetClass
    broker_name: str
    reason: str
    alternatives: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


class SymbolClassifier:
    """Classifies symbols into asset classes.

    This provides default classification based on symbol patterns.
    Can be customized with explicit mappings or external data sources.
    """

    # Default patterns for common exchanges/symbols
    CRYPTO_SUFFIXES = {"USD", "USDT", "BTC", "ETH"}
    ETF_SUFFIXES = {"ETF"}

    # Known ETFs (partial list)
    KNOWN_ETFS = {
        "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "VEA", "VWO",
        "XLF", "XLE", "XLK", "XLV", "XLP", "XLY", "XLI", "XLB", "XLU",
        "GLD", "SLV", "USO", "UNG", "TLT", "IEF", "SHY", "BND",
        "EEM", "EFA", "IEMG", "IEFA", "AGG", "LQD", "HYG", "JNK",
    }

    # Known crypto tickers
    KNOWN_CRYPTO = {
        "BTC", "ETH", "BTCUSD", "ETHUSD", "SOLUSD", "DOGEUSD",
        "AVAXUSD", "LINKUSD", "UNIUSD", "MATICUSD", "ADAUSD",
    }

    def __init__(self):
        """Initialize classifier with custom mappings."""
        self._custom_mappings: Dict[str, AssetClass] = {}
        self._symbol_cache: Dict[str, AssetClass] = {}

    def add_mapping(self, symbol: str, asset_class: AssetClass) -> None:
        """Add a custom symbol-to-class mapping.

        Args:
            symbol: Trading symbol
            asset_class: Asset class for the symbol
        """
        self._custom_mappings[symbol.upper()] = asset_class
        # Invalidate cache for this symbol
        self._symbol_cache.pop(symbol.upper(), None)

    def classify(self, symbol: str) -> AssetClass:
        """Classify a symbol into an asset class.

        Args:
            symbol: Trading symbol

        Returns:
            Detected asset class (defaults to EQUITY)
        """
        symbol = symbol.upper()

        # Check cache first
        if symbol in self._symbol_cache:
            return self._symbol_cache[symbol]

        # Check custom mappings
        if symbol in self._custom_mappings:
            result = self._custom_mappings[symbol]
            self._symbol_cache[symbol] = result
            return result

        # Check known crypto
        if symbol in self.KNOWN_CRYPTO:
            result = AssetClass.CRYPTO
            self._symbol_cache[symbol] = result
            return result

        # Check crypto patterns (ends with crypto currency)
        for suffix in self.CRYPTO_SUFFIXES:
            if symbol.endswith(suffix) and len(symbol) > len(suffix):
                result = AssetClass.CRYPTO
                self._symbol_cache[symbol] = result
                return result

        # Check known ETFs
        if symbol in self.KNOWN_ETFS:
            result = AssetClass.ETF
            self._symbol_cache[symbol] = result
            return result

        # Check futures patterns (month/year codes)
        # E.g., ESZ24 (S&P 500 Dec 2024), CLF25 (Crude Oil Jan 2025)
        if len(symbol) >= 4 and symbol[-2:].isdigit():
            if symbol[-3] in "FGHJKMNQUVXZ":  # Future month codes
                result = AssetClass.FUTURE
                self._symbol_cache[symbol] = result
                return result

        # Check options patterns (contain numbers and special chars)
        if "/" in symbol or ("C" in symbol and symbol[-1].isdigit()):
            result = AssetClass.OPTION
            self._symbol_cache[symbol] = result
            return result

        # Default to equity
        result = AssetClass.EQUITY
        self._symbol_cache[symbol] = result
        return result

    def clear_cache(self) -> None:
        """Clear the classification cache."""
        self._symbol_cache.clear()


class BrokerRouter:
    """Routes orders to appropriate brokers based on asset class.

    The router maintains a registry of brokers and their supported asset
    classes. When an order comes in, it classifies the symbol and routes
    to the appropriate broker.

    Features:
        - Multi-broker support with priority-based selection
        - Automatic symbol classification
        - Custom routing rules
        - Fallback broker support
        - Aggregated position views

    Example:
        >>> router = BrokerRouter()
        >>>
        >>> # Register brokers
        >>> router.register(alpaca, [AssetClass.EQUITY, AssetClass.CRYPTO])
        >>> router.register(ibkr, [AssetClass.FUTURE], primary=True)
        >>>
        >>> # Submit order (auto-routed)
        >>> order = await router.submit_order(
        ...     OrderRequest.market("AAPL", OrderSide.BUY, 100)
        ... )
        >>>
        >>> # Get aggregated positions across all brokers
        >>> positions = await router.get_all_positions()
    """

    def __init__(
        self,
        classifier: Optional[SymbolClassifier] = None,
        default_asset_class: AssetClass = AssetClass.EQUITY,
    ):
        """Initialize the broker router.

        Args:
            classifier: Symbol classifier (creates default if None)
            default_asset_class: Default class for unknown symbols
        """
        self._brokers: Dict[str, BrokerRegistration] = {}
        self._class_to_brokers: Dict[AssetClass, List[str]] = {}
        self._classifier = classifier or SymbolClassifier()
        self._default_asset_class = default_asset_class
        self._fallback_broker: Optional[str] = None
        self._routing_history: List[RoutingDecision] = []
        self._max_history = 1000

    @property
    def registered_brokers(self) -> List[str]:
        """Get list of registered broker names."""
        return list(self._brokers.keys())

    @property
    def supported_asset_classes(self) -> Set[AssetClass]:
        """Get all supported asset classes across all brokers."""
        classes = set()
        for reg in self._brokers.values():
            if reg.enabled:
                classes.update(reg.asset_classes)
        return classes

    def register(
        self,
        broker: BrokerBase,
        asset_classes: Optional[List[AssetClass]] = None,
        priority: int = 0,
        primary: bool = False,
    ) -> None:
        """Register a broker for specific asset classes.

        Args:
            broker: Broker instance to register
            asset_classes: Asset classes this broker handles (uses broker's
                          supported classes if None)
            priority: Priority for routing (higher = preferred)
            primary: Whether this should be the primary broker for its classes

        Raises:
            DuplicateBrokerError: If broker is already registered
        """
        if broker.name in self._brokers:
            raise DuplicateBrokerError(f"Broker '{broker.name}' is already registered")

        # Use broker's supported classes if not specified
        classes = set(asset_classes) if asset_classes else set(broker.supported_asset_classes)

        registration = BrokerRegistration(
            broker=broker,
            asset_classes=classes,
            priority=priority,
            is_primary=primary,
        )

        self._brokers[broker.name] = registration

        # Update class-to-broker mapping
        for asset_class in classes:
            if asset_class not in self._class_to_brokers:
                self._class_to_brokers[asset_class] = []
            self._class_to_brokers[asset_class].append(broker.name)

            # Sort by priority (highest first)
            self._class_to_brokers[asset_class].sort(
                key=lambda n: (
                    self._brokers[n].is_primary,
                    self._brokers[n].priority,
                ),
                reverse=True,
            )

    def unregister(self, broker_name: str) -> None:
        """Unregister a broker.

        Args:
            broker_name: Name of broker to unregister

        Raises:
            BrokerNotFoundError: If broker is not registered
        """
        if broker_name not in self._brokers:
            raise BrokerNotFoundError(f"Broker '{broker_name}' is not registered")

        registration = self._brokers[broker_name]

        # Remove from class mapping
        for asset_class in registration.asset_classes:
            if asset_class in self._class_to_brokers:
                self._class_to_brokers[asset_class].remove(broker_name)
                if not self._class_to_brokers[asset_class]:
                    del self._class_to_brokers[asset_class]

        del self._brokers[broker_name]

        # Clear fallback if it was this broker
        if self._fallback_broker == broker_name:
            self._fallback_broker = None

    def set_fallback(self, broker_name: str) -> None:
        """Set a fallback broker for unclassified symbols.

        Args:
            broker_name: Name of broker to use as fallback

        Raises:
            BrokerNotFoundError: If broker is not registered
        """
        if broker_name not in self._brokers:
            raise BrokerNotFoundError(f"Broker '{broker_name}' is not registered")
        self._fallback_broker = broker_name

    def enable_broker(self, broker_name: str) -> None:
        """Enable a broker for routing.

        Args:
            broker_name: Name of broker to enable

        Raises:
            BrokerNotFoundError: If broker is not registered
        """
        if broker_name not in self._brokers:
            raise BrokerNotFoundError(f"Broker '{broker_name}' is not registered")
        self._brokers[broker_name].enabled = True

    def disable_broker(self, broker_name: str) -> None:
        """Disable a broker from routing.

        Args:
            broker_name: Name of broker to disable

        Raises:
            BrokerNotFoundError: If broker is not registered
        """
        if broker_name not in self._brokers:
            raise BrokerNotFoundError(f"Broker '{broker_name}' is not registered")
        self._brokers[broker_name].enabled = False

    def get_broker(self, broker_name: str) -> BrokerBase:
        """Get a broker by name.

        Args:
            broker_name: Name of broker

        Returns:
            BrokerBase instance

        Raises:
            BrokerNotFoundError: If broker is not registered
        """
        if broker_name not in self._brokers:
            raise BrokerNotFoundError(f"Broker '{broker_name}' is not registered")
        return self._brokers[broker_name].broker

    def route(self, symbol: str) -> Tuple[BrokerBase, RoutingDecision]:
        """Route a symbol to the appropriate broker.

        Args:
            symbol: Trading symbol

        Returns:
            Tuple of (broker, routing_decision)

        Raises:
            NoBrokerError: If no broker can handle this symbol
        """
        # Classify the symbol
        asset_class = self._classifier.classify(symbol)

        # Find brokers for this class
        broker_names = self._class_to_brokers.get(asset_class, [])

        # Filter to enabled brokers
        enabled_names = [
            n for n in broker_names
            if self._brokers[n].enabled
        ]

        # Select the best broker
        if enabled_names:
            broker_name = enabled_names[0]
            reason = f"Primary broker for {asset_class.value}"
            alternatives = enabled_names[1:]
        elif self._fallback_broker and self._brokers[self._fallback_broker].enabled:
            broker_name = self._fallback_broker
            reason = f"Fallback broker (no broker for {asset_class.value})"
            alternatives = []
        else:
            raise NoBrokerError(
                f"No broker available for symbol '{symbol}' "
                f"(asset class: {asset_class.value})"
            )

        decision = RoutingDecision(
            symbol=symbol,
            asset_class=asset_class,
            broker_name=broker_name,
            reason=reason,
            alternatives=alternatives,
        )

        # Record routing history
        self._routing_history.append(decision)
        if len(self._routing_history) > self._max_history:
            self._routing_history = self._routing_history[-self._max_history:]

        return self._brokers[broker_name].broker, decision

    def add_symbol_mapping(self, symbol: str, asset_class: AssetClass) -> None:
        """Add a custom symbol-to-asset-class mapping.

        Args:
            symbol: Trading symbol
            asset_class: Asset class for the symbol
        """
        self._classifier.add_mapping(symbol, asset_class)

    # ==========================================================================
    # Connection Management
    # ==========================================================================

    async def connect_all(self) -> Dict[str, bool]:
        """Connect all registered brokers.

        Returns:
            Dict mapping broker name to connection success
        """
        results = {}
        for name, reg in self._brokers.items():
            try:
                results[name] = await reg.broker.connect()
            except Exception as e:
                results[name] = False
        return results

    async def disconnect_all(self) -> None:
        """Disconnect all registered brokers."""
        for reg in self._brokers.values():
            try:
                await reg.broker.disconnect()
            except Exception:
                pass

    async def is_market_open(self, broker_name: Optional[str] = None) -> bool:
        """Check if market is open.

        Args:
            broker_name: Specific broker to check (checks first enabled if None)

        Returns:
            True if market is open
        """
        if broker_name:
            broker = self.get_broker(broker_name)
            return await broker.is_market_open()

        # Check first enabled broker
        for reg in self._brokers.values():
            if reg.enabled and reg.broker.is_connected:
                return await reg.broker.is_market_open()

        return False

    # ==========================================================================
    # Order Management
    # ==========================================================================

    async def submit_order(
        self,
        request: OrderRequest,
        broker_name: Optional[str] = None,
    ) -> Order:
        """Submit an order, routing to the appropriate broker.

        Args:
            request: Order request
            broker_name: Optional specific broker (auto-routes if None)

        Returns:
            Order object

        Raises:
            NoBrokerError: If no broker can handle this symbol
        """
        if broker_name:
            broker = self.get_broker(broker_name)
        else:
            broker, _ = self.route(request.symbol)

        return await broker.submit_order(request)

    async def cancel_order(
        self,
        order_id: str,
        broker_name: str,
    ) -> Order:
        """Cancel an order.

        Args:
            order_id: Order ID to cancel
            broker_name: Name of broker holding the order

        Returns:
            Updated order
        """
        broker = self.get_broker(broker_name)
        return await broker.cancel_order(order_id)

    async def replace_order(
        self,
        order_id: str,
        broker_name: str,
        quantity: Optional[Decimal] = None,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
    ) -> Order:
        """Replace an order.

        Args:
            order_id: Order ID to replace
            broker_name: Name of broker holding the order
            quantity: New quantity
            limit_price: New limit price
            stop_price: New stop price
            time_in_force: New time in force

        Returns:
            New order
        """
        broker = self.get_broker(broker_name)
        return await broker.replace_order(
            order_id, quantity, limit_price, stop_price, time_in_force
        )

    async def get_order(self, order_id: str, broker_name: str) -> Order:
        """Get an order from a specific broker.

        Args:
            order_id: Order ID
            broker_name: Name of broker

        Returns:
            Order object
        """
        broker = self.get_broker(broker_name)
        return await broker.get_order(order_id)

    async def get_orders(
        self,
        broker_name: Optional[str] = None,
        status: Optional[OrderStatus] = None,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, List[Order]]:
        """Get orders from one or all brokers.

        Args:
            broker_name: Specific broker (all if None)
            status: Filter by status
            symbols: Filter by symbols

        Returns:
            Dict mapping broker name to list of orders
        """
        results = {}

        if broker_name:
            brokers = [(broker_name, self.get_broker(broker_name))]
        else:
            brokers = [
                (name, reg.broker)
                for name, reg in self._brokers.items()
                if reg.enabled and reg.broker.is_connected
            ]

        for name, broker in brokers:
            try:
                orders = await broker.get_orders(status=status, symbols=symbols)
                results[name] = orders
            except Exception:
                results[name] = []

        return results

    async def cancel_all_orders(
        self,
        broker_name: Optional[str] = None,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, List[Order]]:
        """Cancel all orders across one or all brokers.

        Args:
            broker_name: Specific broker (all if None)
            symbols: Filter by symbols

        Returns:
            Dict mapping broker name to list of cancelled orders
        """
        results = {}

        if broker_name:
            brokers = [(broker_name, self.get_broker(broker_name))]
        else:
            brokers = [
                (name, reg.broker)
                for name, reg in self._brokers.items()
                if reg.enabled and reg.broker.is_connected
            ]

        for name, broker in brokers:
            try:
                cancelled = await broker.cancel_all_orders(symbols=symbols)
                results[name] = cancelled
            except Exception:
                results[name] = []

        return results

    # ==========================================================================
    # Position Management
    # ==========================================================================

    async def get_positions(
        self,
        broker_name: Optional[str] = None,
    ) -> Dict[str, List[Position]]:
        """Get positions from one or all brokers.

        Args:
            broker_name: Specific broker (all if None)

        Returns:
            Dict mapping broker name to list of positions
        """
        results = {}

        if broker_name:
            brokers = [(broker_name, self.get_broker(broker_name))]
        else:
            brokers = [
                (name, reg.broker)
                for name, reg in self._brokers.items()
                if reg.enabled and reg.broker.is_connected
            ]

        for name, broker in brokers:
            try:
                positions = await broker.get_positions()
                results[name] = positions
            except Exception:
                results[name] = []

        return results

    async def get_all_positions(self) -> List[Tuple[str, Position]]:
        """Get aggregated positions across all brokers.

        Returns:
            List of (broker_name, position) tuples
        """
        all_positions = []
        positions_by_broker = await self.get_positions()

        for broker_name, positions in positions_by_broker.items():
            for position in positions:
                all_positions.append((broker_name, position))

        return all_positions

    async def get_position(
        self,
        symbol: str,
        broker_name: Optional[str] = None,
    ) -> Optional[Tuple[str, Position]]:
        """Get position for a symbol.

        Args:
            symbol: Trading symbol
            broker_name: Specific broker (searches all if None)

        Returns:
            Tuple of (broker_name, position) or None
        """
        if broker_name:
            broker = self.get_broker(broker_name)
            position = await broker.get_position(symbol)
            if position:
                return (broker_name, position)
            return None

        # Search all brokers
        for name, reg in self._brokers.items():
            if reg.enabled and reg.broker.is_connected:
                try:
                    position = await reg.broker.get_position(symbol)
                    if position:
                        return (name, position)
                except Exception:
                    pass

        return None

    async def close_position(
        self,
        symbol: str,
        broker_name: Optional[str] = None,
        quantity: Optional[Decimal] = None,
    ) -> Order:
        """Close a position.

        Args:
            symbol: Symbol to close
            broker_name: Specific broker (searches if None)
            quantity: Quantity to close (full if None)

        Returns:
            Closing order

        Raises:
            PositionError: If position not found
        """
        result = await self.get_position(symbol, broker_name)
        if result is None:
            raise PositionError(f"No position found for {symbol}")

        actual_broker_name, position = result
        broker = self.get_broker(actual_broker_name)
        return await broker.close_position(symbol, quantity)

    async def close_all_positions(
        self,
        broker_name: Optional[str] = None,
    ) -> Dict[str, List[Order]]:
        """Close all positions across one or all brokers.

        Args:
            broker_name: Specific broker (all if None)

        Returns:
            Dict mapping broker name to list of closing orders
        """
        results = {}

        if broker_name:
            brokers = [(broker_name, self.get_broker(broker_name))]
        else:
            brokers = [
                (name, reg.broker)
                for name, reg in self._brokers.items()
                if reg.enabled and reg.broker.is_connected
            ]

        for name, broker in brokers:
            try:
                orders = await broker.close_all_positions()
                results[name] = orders
            except Exception:
                results[name] = []

        return results

    # ==========================================================================
    # Account Information
    # ==========================================================================

    async def get_accounts(self) -> Dict[str, AccountInfo]:
        """Get account information from all brokers.

        Returns:
            Dict mapping broker name to account info
        """
        results = {}

        for name, reg in self._brokers.items():
            if reg.enabled and reg.broker.is_connected:
                try:
                    results[name] = await reg.broker.get_account()
                except Exception:
                    pass

        return results

    async def get_total_equity(self) -> Decimal:
        """Get total equity across all brokers.

        Returns:
            Total equity value
        """
        total = Decimal("0")
        accounts = await self.get_accounts()

        for account in accounts.values():
            total += account.equity

        return total

    async def get_total_buying_power(self) -> Decimal:
        """Get total buying power across all brokers.

        Returns:
            Total buying power
        """
        total = Decimal("0")
        accounts = await self.get_accounts()

        for account in accounts.values():
            total += account.buying_power

        return total

    # ==========================================================================
    # Market Data
    # ==========================================================================

    async def get_quote(self, symbol: str) -> Quote:
        """Get quote for a symbol from the appropriate broker.

        Args:
            symbol: Trading symbol

        Returns:
            Quote object
        """
        broker, _ = self.route(symbol)
        return await broker.get_quote(symbol)

    async def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """Get quotes for multiple symbols.

        Args:
            symbols: List of symbols

        Returns:
            Dict mapping symbol to quote
        """
        # Group symbols by broker
        broker_symbols: Dict[str, List[str]] = {}
        for symbol in symbols:
            broker, _ = self.route(symbol)
            if broker.name not in broker_symbols:
                broker_symbols[broker.name] = []
            broker_symbols[broker.name].append(symbol)

        # Fetch from each broker
        results = {}
        for broker_name, syms in broker_symbols.items():
            broker = self.get_broker(broker_name)
            broker_quotes = await broker.get_quotes(syms)
            results.update(broker_quotes)

        return results

    async def get_asset(self, symbol: str) -> AssetInfo:
        """Get asset information from the appropriate broker.

        Args:
            symbol: Trading symbol

        Returns:
            AssetInfo object
        """
        broker, _ = self.route(symbol)
        return await broker.get_asset(symbol)

    # ==========================================================================
    # Utility Methods
    # ==========================================================================

    def get_routing_history(
        self,
        limit: int = 100,
        symbol: Optional[str] = None,
    ) -> List[RoutingDecision]:
        """Get routing decision history.

        Args:
            limit: Maximum number of decisions to return
            symbol: Optional filter by symbol

        Returns:
            List of routing decisions (newest first)
        """
        history = self._routing_history[::-1]  # Reverse for newest first

        if symbol:
            history = [d for d in history if d.symbol == symbol]

        return history[:limit]

    def get_broker_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all registered brokers.

        Returns:
            Dict with broker status information
        """
        status = {}

        for name, reg in self._brokers.items():
            status[name] = {
                "connected": reg.broker.is_connected,
                "enabled": reg.enabled,
                "paper_trading": reg.broker.is_paper_trading,
                "asset_classes": [c.value for c in reg.asset_classes],
                "priority": reg.priority,
                "is_primary": reg.is_primary,
                "registered_at": reg.registered_at.isoformat(),
            }

        return status

    def __repr__(self) -> str:
        """String representation."""
        brokers = ", ".join(self._brokers.keys())
        return f"BrokerRouter(brokers=[{brokers}])"
