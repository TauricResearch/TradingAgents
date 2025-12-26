"""Abstract Broker Base Interface.

This module defines the abstract base class for all broker implementations.
Concrete broker implementations (Alpaca, IBKR, Paper) inherit from this class
and implement the abstract methods for their specific APIs.

Issue #22: [EXEC-21] Broker base interface - abstract broker class

Design Principles:
    - Uniform interface across all brokers
    - Async-first for I/O operations
    - Type-safe with dataclasses
    - Support for multiple asset classes
    - Extensible for broker-specific features
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid


class AssetClass(Enum):
    """Supported asset classes."""
    EQUITY = "equity"           # Stocks
    ETF = "etf"                 # Exchange-traded funds
    OPTION = "option"           # Options contracts
    FUTURE = "future"           # Futures contracts
    CRYPTO = "crypto"           # Cryptocurrency
    FOREX = "forex"             # Foreign exchange
    BOND = "bond"               # Fixed income
    INDEX = "index"             # Market indices


class OrderSide(Enum):
    """Order side (buy or sell)."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type.

    MARKET: Execute at current market price
    LIMIT: Execute at specified price or better
    STOP: Trigger market order at stop price
    STOP_LIMIT: Trigger limit order at stop price
    TRAILING_STOP: Stop that trails price by specified amount/percent
    """
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(Enum):
    """Time in force (order duration).

    DAY: Valid until end of regular trading hours
    GTC: Good till cancelled
    IOC: Immediate or cancel (partial fills allowed)
    FOK: Fill or kill (all or nothing)
    OPG: On open (execute at market open)
    CLS: On close (execute at market close)
    GTD: Good till date
    """
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    OPG = "opg"
    CLS = "cls"
    GTD = "gtd"


class OrderStatus(Enum):
    """Order execution status.

    PENDING_NEW: Order submitted, awaiting confirmation
    NEW: Order accepted by broker
    PARTIALLY_FILLED: Order partially executed
    FILLED: Order fully executed
    PENDING_CANCEL: Cancel request submitted
    CANCELLED: Order cancelled
    REJECTED: Order rejected by broker
    EXPIRED: Order expired (time in force elapsed)
    REPLACED: Order was replaced by new order
    """
    PENDING_NEW = "pending_new"
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    PENDING_CANCEL = "pending_cancel"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REPLACED = "replaced"


class PositionSide(Enum):
    """Position side."""
    LONG = "long"
    SHORT = "short"


@dataclass
class OrderRequest:
    """Request to submit an order.

    Attributes:
        symbol: Trading symbol
        side: Buy or sell
        quantity: Number of shares/contracts
        order_type: Type of order
        limit_price: Limit price (for limit/stop-limit orders)
        stop_price: Stop price (for stop/stop-limit orders)
        time_in_force: Order duration
        client_order_id: Optional client-defined order ID
        extended_hours: Allow extended hours trading
        trail_amount: Trail amount for trailing stop (absolute)
        trail_percent: Trail percent for trailing stop
        take_profit_price: Take profit price (OCO orders)
        stop_loss_price: Stop loss price (OCO orders)
        metadata: Additional broker-specific metadata
    """
    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    client_order_id: Optional[str] = None
    extended_hours: bool = False
    trail_amount: Optional[Decimal] = None
    trail_percent: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    stop_loss_price: Optional[Decimal] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Generate client order ID if not provided."""
        if self.client_order_id is None:
            self.client_order_id = str(uuid.uuid4())

        # Validate order type requirements
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("Limit orders require limit_price")
        if self.order_type == OrderType.STOP and self.stop_price is None:
            raise ValueError("Stop orders require stop_price")
        if self.order_type == OrderType.STOP_LIMIT:
            if self.limit_price is None or self.stop_price is None:
                raise ValueError("Stop-limit orders require both limit_price and stop_price")
        if self.order_type == OrderType.TRAILING_STOP:
            if self.trail_amount is None and self.trail_percent is None:
                raise ValueError("Trailing stop orders require trail_amount or trail_percent")

    @classmethod
    def market(
        cls,
        symbol: str,
        side: OrderSide,
        quantity: Union[Decimal, float, int],
        time_in_force: TimeInForce = TimeInForce.DAY,
        **kwargs,
    ) -> "OrderRequest":
        """Create a market order request."""
        return cls(
            symbol=symbol,
            side=side,
            quantity=Decimal(str(quantity)),
            order_type=OrderType.MARKET,
            time_in_force=time_in_force,
            **kwargs,
        )

    @classmethod
    def limit(
        cls,
        symbol: str,
        side: OrderSide,
        quantity: Union[Decimal, float, int],
        limit_price: Union[Decimal, float, int],
        time_in_force: TimeInForce = TimeInForce.GTC,
        **kwargs,
    ) -> "OrderRequest":
        """Create a limit order request."""
        return cls(
            symbol=symbol,
            side=side,
            quantity=Decimal(str(quantity)),
            order_type=OrderType.LIMIT,
            limit_price=Decimal(str(limit_price)),
            time_in_force=time_in_force,
            **kwargs,
        )

    @classmethod
    def stop(
        cls,
        symbol: str,
        side: OrderSide,
        quantity: Union[Decimal, float, int],
        stop_price: Union[Decimal, float, int],
        time_in_force: TimeInForce = TimeInForce.GTC,
        **kwargs,
    ) -> "OrderRequest":
        """Create a stop order request."""
        return cls(
            symbol=symbol,
            side=side,
            quantity=Decimal(str(quantity)),
            order_type=OrderType.STOP,
            stop_price=Decimal(str(stop_price)),
            time_in_force=time_in_force,
            **kwargs,
        )

    @classmethod
    def stop_limit(
        cls,
        symbol: str,
        side: OrderSide,
        quantity: Union[Decimal, float, int],
        stop_price: Union[Decimal, float, int],
        limit_price: Union[Decimal, float, int],
        time_in_force: TimeInForce = TimeInForce.GTC,
        **kwargs,
    ) -> "OrderRequest":
        """Create a stop-limit order request."""
        return cls(
            symbol=symbol,
            side=side,
            quantity=Decimal(str(quantity)),
            order_type=OrderType.STOP_LIMIT,
            stop_price=Decimal(str(stop_price)),
            limit_price=Decimal(str(limit_price)),
            time_in_force=time_in_force,
            **kwargs,
        )

    @classmethod
    def trailing_stop(
        cls,
        symbol: str,
        side: OrderSide,
        quantity: Union[Decimal, float, int],
        trail_percent: Optional[Union[Decimal, float]] = None,
        trail_amount: Optional[Union[Decimal, float]] = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        **kwargs,
    ) -> "OrderRequest":
        """Create a trailing stop order request."""
        return cls(
            symbol=symbol,
            side=side,
            quantity=Decimal(str(quantity)),
            order_type=OrderType.TRAILING_STOP,
            trail_percent=Decimal(str(trail_percent)) if trail_percent else None,
            trail_amount=Decimal(str(trail_amount)) if trail_amount else None,
            time_in_force=time_in_force,
            **kwargs,
        )


@dataclass
class Order:
    """Order information returned from broker.

    Attributes:
        broker_order_id: Broker-assigned order ID
        client_order_id: Client-assigned order ID
        symbol: Trading symbol
        side: Buy or sell
        quantity: Ordered quantity
        order_type: Type of order
        status: Current order status
        limit_price: Limit price (if applicable)
        stop_price: Stop price (if applicable)
        time_in_force: Order duration
        filled_quantity: Quantity filled so far
        filled_avg_price: Average fill price
        created_at: Order creation timestamp
        updated_at: Last update timestamp
        submitted_at: Submission timestamp
        filled_at: Fill completion timestamp (if filled)
        cancelled_at: Cancellation timestamp (if cancelled)
        expired_at: Expiration timestamp (if expired)
        extended_hours: Whether extended hours allowed
        trail_amount: Trail amount (if trailing stop)
        trail_percent: Trail percent (if trailing stop)
        legs: Child orders (for bracket/OCO orders)
        reject_reason: Reason for rejection (if rejected)
        metadata: Additional broker-specific data
    """
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    status: OrderStatus
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    filled_quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    filled_avg_price: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    extended_hours: bool = False
    trail_amount: Optional[Decimal] = None
    trail_percent: Optional[Decimal] = None
    legs: List["Order"] = field(default_factory=list)
    reject_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        """Check if order is still open."""
        return self.status in (
            OrderStatus.PENDING_NEW,
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.PENDING_CANCEL,
        )

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED

    @property
    def is_cancelled(self) -> bool:
        """Check if order is cancelled."""
        return self.status == OrderStatus.CANCELLED

    @property
    def remaining_quantity(self) -> Decimal:
        """Calculate remaining unfilled quantity."""
        return self.quantity - self.filled_quantity

    @property
    def fill_percent(self) -> float:
        """Calculate fill percentage."""
        if self.quantity == 0:
            return 0.0
        return float(self.filled_quantity / self.quantity * 100)


@dataclass
class Position:
    """Current position in an asset.

    Attributes:
        symbol: Trading symbol
        quantity: Position quantity (positive for long, negative for short)
        side: Position side (long/short)
        avg_entry_price: Average entry price
        current_price: Current market price
        market_value: Current market value
        cost_basis: Total cost basis
        unrealized_pnl: Unrealized profit/loss
        unrealized_pnl_percent: Unrealized P&L as percentage
        realized_pnl: Realized profit/loss (if tracked)
        asset_class: Asset class
        exchange: Exchange where traded
        asset_id: Broker's asset ID
        metadata: Additional broker-specific data
    """
    symbol: str
    quantity: Decimal
    side: PositionSide
    avg_entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percent: Decimal
    realized_pnl: Optional[Decimal] = None
    asset_class: AssetClass = AssetClass.EQUITY
    exchange: Optional[str] = None
    asset_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.side == PositionSide.LONG

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.side == PositionSide.SHORT

    @property
    def abs_quantity(self) -> Decimal:
        """Get absolute quantity."""
        return abs(self.quantity)


@dataclass
class AccountInfo:
    """Broker account information.

    Attributes:
        account_id: Broker account ID
        account_type: Account type (e.g., 'cash', 'margin')
        status: Account status
        currency: Base currency
        cash: Available cash balance
        portfolio_value: Total portfolio value
        buying_power: Available buying power
        equity: Account equity
        margin_used: Margin currently in use
        margin_available: Available margin
        initial_margin: Initial margin requirement
        maintenance_margin: Maintenance margin requirement
        pending_transfer_in: Pending incoming transfers
        pending_transfer_out: Pending outgoing transfers
        day_trades_remaining: PDT day trades remaining (if applicable)
        is_pattern_day_trader: Whether flagged as PDT
        created_at: Account creation date
        metadata: Additional broker-specific data
    """
    account_id: str
    account_type: str
    status: str
    currency: str = "USD"
    cash: Decimal = field(default_factory=lambda: Decimal("0"))
    portfolio_value: Decimal = field(default_factory=lambda: Decimal("0"))
    buying_power: Decimal = field(default_factory=lambda: Decimal("0"))
    equity: Decimal = field(default_factory=lambda: Decimal("0"))
    margin_used: Optional[Decimal] = None
    margin_available: Optional[Decimal] = None
    initial_margin: Optional[Decimal] = None
    maintenance_margin: Optional[Decimal] = None
    pending_transfer_in: Optional[Decimal] = None
    pending_transfer_out: Optional[Decimal] = None
    day_trades_remaining: Optional[int] = None
    is_pattern_day_trader: bool = False
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Check if account is active."""
        return self.status.lower() in ("active", "approved", "enabled")


@dataclass
class Quote:
    """Current quote/price data.

    Attributes:
        symbol: Trading symbol
        bid_price: Current bid price
        bid_size: Bid size
        ask_price: Current ask price
        ask_size: Ask size
        last_price: Last trade price
        last_size: Last trade size
        volume: Trading volume
        timestamp: Quote timestamp
        exchange: Exchange code
        conditions: Trade conditions
        metadata: Additional data
    """
    symbol: str
    bid_price: Optional[Decimal] = None
    bid_size: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    ask_size: Optional[Decimal] = None
    last_price: Optional[Decimal] = None
    last_size: Optional[Decimal] = None
    volume: Optional[int] = None
    timestamp: Optional[datetime] = None
    exchange: Optional[str] = None
    conditions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def mid_price(self) -> Optional[Decimal]:
        """Calculate mid price between bid and ask."""
        if self.bid_price is not None and self.ask_price is not None:
            return (self.bid_price + self.ask_price) / 2
        return self.last_price

    @property
    def spread(self) -> Optional[Decimal]:
        """Calculate bid-ask spread."""
        if self.bid_price is not None and self.ask_price is not None:
            return self.ask_price - self.bid_price
        return None

    @property
    def spread_percent(self) -> Optional[float]:
        """Calculate spread as percentage of mid price."""
        if self.spread is not None and self.mid_price is not None and self.mid_price > 0:
            return float(self.spread / self.mid_price * 100)
        return None


@dataclass
class AssetInfo:
    """Asset/instrument information.

    Attributes:
        symbol: Trading symbol
        name: Full name
        asset_class: Asset class
        exchange: Primary exchange
        tradable: Whether currently tradable
        marginable: Whether marginable
        shortable: Whether shortable
        easy_to_borrow: Whether easy to borrow for shorting
        fractionable: Whether fractional shares allowed
        min_order_size: Minimum order size
        min_trade_increment: Minimum trade increment
        price_increment: Price increment (tick size)
        maintenance_margin_req: Maintenance margin requirement
        attributes: Additional attributes list
        metadata: Additional broker-specific data
    """
    symbol: str
    name: str
    asset_class: AssetClass = AssetClass.EQUITY
    exchange: Optional[str] = None
    tradable: bool = True
    marginable: bool = True
    shortable: bool = True
    easy_to_borrow: bool = True
    fractionable: bool = False
    min_order_size: Optional[Decimal] = None
    min_trade_increment: Optional[Decimal] = None
    price_increment: Optional[Decimal] = None
    maintenance_margin_req: Optional[Decimal] = None
    attributes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BrokerError(Exception):
    """Base exception for broker errors."""

    def __init__(self, message: str, code: Optional[str] = None, details: Optional[Dict] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class ConnectionError(BrokerError):
    """Error connecting to broker."""
    pass


class AuthenticationError(BrokerError):
    """Authentication failed."""
    pass


class OrderError(BrokerError):
    """Error submitting or managing order."""
    pass


class InsufficientFundsError(OrderError):
    """Insufficient funds for order."""
    pass


class InvalidOrderError(OrderError):
    """Invalid order parameters."""
    pass


class PositionError(BrokerError):
    """Error with position operations."""
    pass


class RateLimitError(BrokerError):
    """Rate limit exceeded."""

    def __init__(self, message: str, retry_after: Optional[float] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class BrokerBase(ABC):
    """Abstract base class for broker implementations.

    All broker implementations must inherit from this class and implement
    the abstract methods. This provides a uniform interface for the trading
    system regardless of which broker is used.

    Example:
        >>> class AlpacaBroker(BrokerBase):
        ...     async def connect(self) -> bool:
        ...         # Connect to Alpaca API
        ...         return True
        ...     # ... implement other abstract methods
        >>>
        >>> broker = AlpacaBroker(api_key="...", api_secret="...")
        >>> await broker.connect()
        >>> order = await broker.submit_order(
        ...     OrderRequest.market("AAPL", OrderSide.BUY, 100)
        ... )
    """

    def __init__(
        self,
        name: str,
        supported_asset_classes: Optional[List[AssetClass]] = None,
        paper_trading: bool = False,
        **kwargs,
    ):
        """Initialize broker base.

        Args:
            name: Broker name
            supported_asset_classes: List of supported asset classes
            paper_trading: Whether this is paper trading mode
            **kwargs: Additional broker-specific configuration
        """
        self._name = name
        self._supported_asset_classes = supported_asset_classes or [AssetClass.EQUITY]
        self._paper_trading = paper_trading
        self._connected = False
        self._config = kwargs

    @property
    def name(self) -> str:
        """Get broker name."""
        return self._name

    @property
    def supported_asset_classes(self) -> List[AssetClass]:
        """Get list of supported asset classes."""
        return self._supported_asset_classes

    @property
    def is_paper_trading(self) -> bool:
        """Check if broker is in paper trading mode."""
        return self._paper_trading

    @property
    def is_connected(self) -> bool:
        """Check if broker is connected."""
        return self._connected

    def supports_asset_class(self, asset_class: AssetClass) -> bool:
        """Check if broker supports a specific asset class.

        Args:
            asset_class: Asset class to check

        Returns:
            True if supported, False otherwise
        """
        return asset_class in self._supported_asset_classes

    # ==========================================================================
    # Connection Management
    # ==========================================================================

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to broker API.

        Returns:
            True if connection successful, False otherwise

        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If authentication fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from broker API."""
        pass

    @abstractmethod
    async def is_market_open(self) -> bool:
        """Check if market is currently open.

        Returns:
            True if market is open, False otherwise
        """
        pass

    # ==========================================================================
    # Account Information
    # ==========================================================================

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Get account information.

        Returns:
            AccountInfo object with account details

        Raises:
            ConnectionError: If not connected
            BrokerError: If account retrieval fails
        """
        pass

    # ==========================================================================
    # Order Management
    # ==========================================================================

    @abstractmethod
    async def submit_order(self, request: OrderRequest) -> Order:
        """Submit a new order.

        Args:
            request: Order request details

        Returns:
            Order object representing submitted order

        Raises:
            ConnectionError: If not connected
            InvalidOrderError: If order parameters invalid
            InsufficientFundsError: If insufficient buying power
            OrderError: If order submission fails
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> Order:
        """Cancel an existing order.

        Args:
            order_id: Broker order ID to cancel

        Returns:
            Updated order object

        Raises:
            OrderError: If cancellation fails
        """
        pass

    @abstractmethod
    async def replace_order(
        self,
        order_id: str,
        quantity: Optional[Decimal] = None,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
    ) -> Order:
        """Replace/modify an existing order.

        Args:
            order_id: Broker order ID to replace
            quantity: New quantity (optional)
            limit_price: New limit price (optional)
            stop_price: New stop price (optional)
            time_in_force: New time in force (optional)

        Returns:
            New order object

        Raises:
            OrderError: If replacement fails
        """
        pass

    @abstractmethod
    async def get_order(self, order_id: str) -> Order:
        """Get order by ID.

        Args:
            order_id: Broker order ID

        Returns:
            Order object

        Raises:
            OrderError: If order not found
        """
        pass

    @abstractmethod
    async def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        limit: int = 100,
        symbols: Optional[List[str]] = None,
    ) -> List[Order]:
        """Get orders with optional filters.

        Args:
            status: Filter by order status
            limit: Maximum number of orders to return
            symbols: Filter by symbols

        Returns:
            List of Order objects
        """
        pass

    async def cancel_all_orders(self, symbols: Optional[List[str]] = None) -> List[Order]:
        """Cancel all open orders.

        Args:
            symbols: Optional list of symbols to cancel orders for

        Returns:
            List of cancelled orders
        """
        open_orders = await self.get_orders(
            status=OrderStatus.NEW,
            symbols=symbols,
        )

        # Also get partially filled orders
        partial_orders = await self.get_orders(
            status=OrderStatus.PARTIALLY_FILLED,
            symbols=symbols,
        )

        cancelled = []
        for order in open_orders + partial_orders:
            try:
                cancelled_order = await self.cancel_order(order.broker_order_id)
                cancelled.append(cancelled_order)
            except OrderError:
                # Order may have been filled between query and cancel
                pass

        return cancelled

    # ==========================================================================
    # Position Management
    # ==========================================================================

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Get all current positions.

        Returns:
            List of Position objects
        """
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position object or None if no position
        """
        pass

    async def close_position(
        self,
        symbol: str,
        quantity: Optional[Decimal] = None,
    ) -> Order:
        """Close a position partially or completely.

        Args:
            symbol: Symbol to close
            quantity: Quantity to close (None for entire position)

        Returns:
            Order object for the closing trade

        Raises:
            PositionError: If position doesn't exist
        """
        position = await self.get_position(symbol)
        if position is None:
            raise PositionError(f"No position found for {symbol}")

        close_qty = quantity if quantity is not None else position.abs_quantity

        # Determine side based on position
        side = OrderSide.SELL if position.is_long else OrderSide.BUY

        return await self.submit_order(
            OrderRequest.market(symbol, side, close_qty)
        )

    async def close_all_positions(self) -> List[Order]:
        """Close all positions.

        Returns:
            List of orders for closing trades
        """
        positions = await self.get_positions()
        orders = []

        for position in positions:
            try:
                order = await self.close_position(position.symbol)
                orders.append(order)
            except (OrderError, PositionError):
                # Position may have been closed between query and close
                pass

        return orders

    # ==========================================================================
    # Market Data
    # ==========================================================================

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Get current quote for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Quote object with bid/ask/last prices
        """
        pass

    async def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """Get quotes for multiple symbols.

        Default implementation calls get_quote for each symbol.
        Override for batch operations if supported by broker.

        Args:
            symbols: List of trading symbols

        Returns:
            Dict mapping symbol to Quote
        """
        quotes = {}
        for symbol in symbols:
            try:
                quotes[symbol] = await self.get_quote(symbol)
            except BrokerError:
                pass
        return quotes

    @abstractmethod
    async def get_asset(self, symbol: str) -> AssetInfo:
        """Get asset information.

        Args:
            symbol: Trading symbol

        Returns:
            AssetInfo object with asset details
        """
        pass

    # ==========================================================================
    # Utility Methods
    # ==========================================================================

    async def validate_order(self, request: OrderRequest) -> List[str]:
        """Validate an order request before submission.

        Args:
            request: Order request to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check basic parameters
        if request.quantity <= 0:
            errors.append("Quantity must be positive")

        # Check asset is tradable
        try:
            asset = await self.get_asset(request.symbol)
            if not asset.tradable:
                errors.append(f"{request.symbol} is not currently tradable")
        except BrokerError:
            errors.append(f"Could not validate asset {request.symbol}")

        # Check limit price for limit orders
        if request.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            if request.limit_price is None or request.limit_price <= 0:
                errors.append("Limit price must be positive for limit orders")

        # Check stop price for stop orders
        if request.order_type in (OrderType.STOP, OrderType.STOP_LIMIT, OrderType.TRAILING_STOP):
            if request.order_type != OrderType.TRAILING_STOP:
                if request.stop_price is None or request.stop_price <= 0:
                    errors.append("Stop price must be positive for stop orders")

        # Check buying power
        if request.side == OrderSide.BUY:
            try:
                account = await self.get_account()
                quote = await self.get_quote(request.symbol)
                estimated_cost = request.quantity * (
                    request.limit_price or quote.ask_price or quote.last_price or Decimal("0")
                )
                if estimated_cost > account.buying_power:
                    errors.append(
                        f"Insufficient buying power. Required: {estimated_cost}, "
                        f"Available: {account.buying_power}"
                    )
            except BrokerError:
                pass  # Skip buying power check if we can't get data

        return errors

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"{self.__class__.__name__}("
            f"name='{self._name}', "
            f"paper_trading={self._paper_trading}, "
            f"connected={self._connected})"
        )
