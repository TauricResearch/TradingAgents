"""Paper Broker implementation for simulation trading.

Issue #26: [EXEC-25] Paper broker - simulation mode

This module provides a simulated broker for paper trading, backtesting,
and testing without real API connections. It simulates order execution,
position tracking, and account management.

Features:
    - Simulated order execution with configurable fill behavior
    - Position tracking with P&L calculations
    - Account balance management
    - Slippage simulation
    - Market data simulation
    - No external dependencies required

Example:
    >>> from tradingagents.execution import PaperBroker, OrderRequest, OrderSide
    >>>
    >>> broker = PaperBroker(
    ...     initial_cash=100000,
    ...     slippage_percent=0.05,
    ... )
    >>>
    >>> await broker.connect()
    >>> order = await broker.submit_order(
    ...     OrderRequest.market("AAPL", OrderSide.BUY, 100)
    ... )
    >>> print(f"Order filled at {order.avg_fill_price}")
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Callable

from .broker_base import (
    AccountInfo,
    AssetClass,
    AssetInfo,
    AuthenticationError,
    BrokerBase,
    BrokerError,
    ConnectionError,
    InsufficientFundsError,
    InvalidOrderError,
    Order,
    OrderError,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionError,
    PositionSide,
    Quote,
    RateLimitError,
    TimeInForce,
)


class PaperBroker(BrokerBase):
    """Simulated paper trading broker.

    Provides a fully simulated trading environment for testing,
    backtesting, and paper trading without any real API connections.

    Attributes:
        initial_cash: Starting cash balance
        slippage_percent: Slippage applied to fills (0.05 = 0.05%)
        fill_probability: Probability of order fills (0.0-1.0)
        market_open: Whether market is simulated as open

    Example:
        >>> broker = PaperBroker(initial_cash=100000)
        >>> await broker.connect()
        >>> order = await broker.submit_order(
        ...     OrderRequest.market("AAPL", OrderSide.BUY, 10)
        ... )
        >>> positions = await broker.get_positions()
    """

    def __init__(
        self,
        initial_cash: Decimal = Decimal("100000"),
        slippage_percent: Decimal = Decimal("0.05"),
        fill_probability: float = 1.0,
        market_open: bool = True,
        price_provider: Optional[Callable[[str], Decimal]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize paper broker.

        Args:
            initial_cash: Starting cash balance (default: 100,000)
            slippage_percent: Slippage as percentage (default: 0.05%)
            fill_probability: Probability of fills (default: 1.0 = 100%)
            market_open: Whether to simulate market as open
            price_provider: Optional function to get prices for symbols
            **kwargs: Additional arguments passed to BrokerBase.
        """
        super().__init__(
            name="Paper",
            supported_asset_classes=[
                AssetClass.EQUITY,
                AssetClass.ETF,
                AssetClass.CRYPTO,
                AssetClass.FUTURE,
                AssetClass.OPTION,
                AssetClass.FOREX,
            ],
            paper_trading=True,
            **kwargs,
        )

        self._initial_cash = Decimal(str(initial_cash))
        self._cash = self._initial_cash
        self._slippage_percent = Decimal(str(slippage_percent))
        self._fill_probability = fill_probability
        self._market_open = market_open
        self._price_provider = price_provider

        # Internal state
        self._orders: Dict[str, Order] = {}
        self._positions: Dict[str, Position] = {}
        self._order_counter = 0

        # Simulated price cache
        self._prices: Dict[str, Decimal] = {}

        # Default prices for common symbols
        self._default_prices = {
            "AAPL": Decimal("175.00"),
            "MSFT": Decimal("380.00"),
            "GOOGL": Decimal("140.00"),
            "AMZN": Decimal("155.00"),
            "NVDA": Decimal("480.00"),
            "META": Decimal("360.00"),
            "TSLA": Decimal("250.00"),
            "SPY": Decimal("470.00"),
            "QQQ": Decimal("400.00"),
            "IWM": Decimal("200.00"),
            "BTCUSD": Decimal("45000.00"),
            "ETHUSD": Decimal("2500.00"),
            "ES": Decimal("4700.00"),
            "NQ": Decimal("16500.00"),
        }

    @property
    def cash(self) -> Decimal:
        """Get current cash balance."""
        return self._cash

    @property
    def initial_cash(self) -> Decimal:
        """Get initial cash balance."""
        return self._initial_cash

    def set_price(self, symbol: str, price: Decimal) -> None:
        """Set simulated price for a symbol.

        Args:
            symbol: Symbol to set price for
            price: Price to set
        """
        self._prices[symbol] = Decimal(str(price))

    def get_simulated_price(self, symbol: str) -> Decimal:
        """Get simulated price for a symbol.

        Args:
            symbol: Symbol to get price for

        Returns:
            Simulated price
        """
        # Check custom price provider first
        if self._price_provider:
            return self._price_provider(symbol)

        # Check cached prices
        if symbol in self._prices:
            return self._prices[symbol]

        # Check default prices
        if symbol in self._default_prices:
            return self._default_prices[symbol]

        # Generate random price for unknown symbols
        return Decimal("100.00") + Decimal(str(random.uniform(-10, 10)))

    def _require_connection(self) -> None:
        """Require broker to be connected."""
        if not self.is_connected:
            raise ConnectionError("Not connected to Paper broker. Call connect() first.")

    async def connect(self) -> bool:
        """Connect to paper broker (always succeeds).

        Returns:
            True always
        """
        self._connected = True
        return True

    async def disconnect(self) -> None:
        """Disconnect from paper broker."""
        self._connected = False

    async def is_market_open(self) -> bool:
        """Check if simulated market is open.

        Returns:
            The configured market_open value
        """
        return self._market_open

    def set_market_open(self, is_open: bool) -> None:
        """Set market open status.

        Args:
            is_open: Whether market should be open
        """
        self._market_open = is_open

    async def get_account(self) -> AccountInfo:
        """Get simulated account information.

        Returns:
            AccountInfo with current simulated account state.
        """
        self._require_connection()

        # Calculate portfolio value
        portfolio_value = self._cash
        for position in self._positions.values():
            portfolio_value += position.market_value

        return AccountInfo(
            account_id="PAPER-" + str(uuid.uuid4())[:8].upper(),
            account_type="paper",
            status="active",
            cash=self._cash,
            portfolio_value=portfolio_value,
            buying_power=self._cash,  # Simplified: no margin
            equity=portfolio_value,
        )

    def _generate_order_id(self) -> str:
        """Generate unique order ID."""
        self._order_counter += 1
        return f"PAPER-{self._order_counter}-{uuid.uuid4().hex[:8]}"

    def _calculate_fill_price(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        limit_price: Optional[Decimal] = None,
    ) -> Optional[Decimal]:
        """Calculate fill price with slippage.

        Args:
            symbol: Symbol being traded
            side: Order side
            order_type: Order type
            limit_price: Limit price if applicable

        Returns:
            Fill price or None if order shouldn't fill
        """
        base_price = self.get_simulated_price(symbol)

        if order_type == OrderType.LIMIT:
            if limit_price is None:
                return None
            # For limit orders, check if price is favorable
            if side == OrderSide.BUY:
                if base_price > limit_price:
                    return None  # Market price above limit
                return limit_price
            else:
                if base_price < limit_price:
                    return None  # Market price below limit
                return limit_price

        # Apply slippage for market orders
        slippage_factor = self._slippage_percent / Decimal("100")
        if side == OrderSide.BUY:
            # Slippage increases price for buys
            fill_price = base_price * (Decimal("1") + slippage_factor)
        else:
            # Slippage decreases price for sells
            fill_price = base_price * (Decimal("1") - slippage_factor)

        return fill_price.quantize(Decimal("0.01"))

    def _should_fill(self) -> bool:
        """Determine if order should fill based on fill probability."""
        return random.random() < self._fill_probability

    def _update_position(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        fill_price: Decimal,
    ) -> None:
        """Update position after fill.

        Args:
            symbol: Symbol traded
            side: Order side
            quantity: Quantity filled
            fill_price: Fill price
        """
        if symbol in self._positions:
            position = self._positions[symbol]

            if side == OrderSide.BUY:
                # Add to position
                new_quantity = position.quantity + quantity
                total_cost = (position.avg_entry_price * position.quantity) + (fill_price * quantity)
                new_avg_price = total_cost / new_quantity if new_quantity > 0 else fill_price
                position.quantity = new_quantity
                position.avg_entry_price = new_avg_price
            else:
                # Reduce position
                position.quantity -= quantity
                if position.quantity <= 0:
                    del self._positions[symbol]
                    return

            # Update market value and P&L
            current_price = self.get_simulated_price(symbol)
            position.current_price = current_price
            position.market_value = position.quantity * current_price
            position.cost_basis = position.quantity * position.avg_entry_price
            position.unrealized_pnl = position.market_value - position.cost_basis
            if position.cost_basis > 0:
                position.unrealized_pnl_percent = (
                    position.unrealized_pnl / position.cost_basis * Decimal("100")
                )
        else:
            if side == OrderSide.BUY:
                # Create new long position
                current_price = self.get_simulated_price(symbol)
                self._positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity,
                    side=PositionSide.LONG,
                    avg_entry_price=fill_price,
                    current_price=current_price,
                    market_value=quantity * current_price,
                    cost_basis=quantity * fill_price,
                    unrealized_pnl=quantity * (current_price - fill_price),
                    unrealized_pnl_percent=(
                        (current_price - fill_price) / fill_price * Decimal("100")
                        if fill_price > 0 else Decimal("0")
                    ),
                )
            # For sells without existing position, we'd need short selling logic
            # For simplicity, ignore sells without positions

    async def submit_order(self, request: OrderRequest) -> Order:
        """Submit a simulated order.

        Args:
            request: Order request details.

        Returns:
            Order with execution details.

        Raises:
            InvalidOrderError: If order parameters are invalid.
            InsufficientFundsError: If insufficient funds.
        """
        self._require_connection()

        # Validate order
        if request.quantity <= 0:
            raise InvalidOrderError("Order quantity must be positive")

        # Generate order ID
        order_id = self._generate_order_id()

        # Calculate fill price
        fill_price = self._calculate_fill_price(
            request.symbol,
            request.side,
            request.order_type,
            request.limit_price,
        )

        # Determine if order should fill
        should_fill = self._should_fill() and fill_price is not None

        if should_fill:
            # Check funds for buys
            if request.side == OrderSide.BUY:
                required_funds = request.quantity * fill_price
                if required_funds > self._cash:
                    raise InsufficientFundsError(
                        f"Insufficient funds: need ${required_funds}, have ${self._cash}"
                    )
                # Deduct cash
                self._cash -= required_funds

            # For sells, add cash back
            else:
                proceeds = request.quantity * fill_price
                self._cash += proceeds

            # Update position
            self._update_position(
                request.symbol,
                request.side,
                request.quantity,
                fill_price,
            )

            status = OrderStatus.FILLED
            filled_qty = request.quantity
            avg_fill = fill_price
            filled_at = datetime.now(timezone.utc)
        else:
            status = OrderStatus.NEW
            filled_qty = Decimal("0")
            avg_fill = None
            filled_at = None

        # Create order
        order = Order(
            broker_order_id=order_id,
            client_order_id=request.client_order_id or "",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            status=status,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            time_in_force=request.time_in_force,
            filled_quantity=filled_qty,
            filled_avg_price=avg_fill,
            created_at=datetime.now(timezone.utc),
            filled_at=filled_at,
        )

        self._orders[order_id] = order
        return order

    async def cancel_order(self, order_id: str) -> Order:
        """Cancel a simulated order.

        Args:
            order_id: Order ID to cancel.

        Returns:
            Cancelled order.

        Raises:
            OrderError: If order not found or cannot be cancelled.
        """
        self._require_connection()

        if order_id not in self._orders:
            raise OrderError(f"Order {order_id} not found")

        order = self._orders[order_id]

        # Can only cancel unfilled orders
        if order.status == OrderStatus.FILLED:
            raise OrderError("Cannot cancel filled order")

        order.status = OrderStatus.CANCELLED
        order.cancelled_at = datetime.now(timezone.utc)

        return order

    async def replace_order(
        self,
        order_id: str,
        quantity: Optional[Decimal] = None,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
    ) -> Order:
        """Replace a simulated order.

        Creates a new order with updated parameters.
        """
        self._require_connection()

        if order_id not in self._orders:
            raise OrderError(f"Order {order_id} not found")

        old_order = self._orders[order_id]

        # Cancel old order
        if old_order.status != OrderStatus.FILLED:
            old_order.status = OrderStatus.REPLACED

        # Create new order request
        request = OrderRequest(
            symbol=old_order.symbol,
            side=old_order.side,
            quantity=quantity or old_order.quantity,
            order_type=old_order.order_type,
            time_in_force=time_in_force or old_order.time_in_force,
            limit_price=limit_price or old_order.limit_price,
            stop_price=stop_price or old_order.stop_price,
        )

        return await self.submit_order(request)

    async def get_order(self, order_id: str) -> Order:
        """Get order by ID.

        Args:
            order_id: Order ID.

        Returns:
            Order details.

        Raises:
            OrderError: If order not found.
        """
        self._require_connection()

        if order_id not in self._orders:
            raise OrderError(f"Order {order_id} not found")

        return self._orders[order_id]

    async def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        limit: int = 100,
        symbols: Optional[List[str]] = None,
    ) -> List[Order]:
        """Get orders with optional filters.

        Args:
            status: Filter by status.
            limit: Maximum number to return.
            symbols: Filter by symbols.

        Returns:
            List of matching orders.
        """
        self._require_connection()

        orders = list(self._orders.values())

        # Apply filters
        if status:
            orders = [o for o in orders if o.status == status]
        if symbols:
            orders = [o for o in orders if o.symbol in symbols]

        # Sort by creation time, most recent first
        orders.sort(key=lambda o: o.created_at or datetime.min, reverse=True)

        return orders[:limit]

    async def get_positions(self) -> List[Position]:
        """Get all positions.

        Returns:
            List of current positions.
        """
        self._require_connection()

        # Update current prices
        for symbol, position in self._positions.items():
            current_price = self.get_simulated_price(symbol)
            position.current_price = current_price
            position.market_value = position.quantity * current_price
            position.unrealized_pnl = position.market_value - position.cost_basis
            if position.cost_basis > 0:
                position.unrealized_pnl_percent = (
                    position.unrealized_pnl / position.cost_basis * Decimal("100")
                )

        return list(self._positions.values())

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol.

        Args:
            symbol: Symbol to get position for.

        Returns:
            Position if exists, None otherwise.
        """
        self._require_connection()

        if symbol in self._positions:
            position = self._positions[symbol]
            # Update current price
            current_price = self.get_simulated_price(symbol)
            position.current_price = current_price
            position.market_value = position.quantity * current_price
            position.unrealized_pnl = position.market_value - position.cost_basis
            return position

        return None

    async def get_quote(self, symbol: str) -> Quote:
        """Get simulated quote.

        Args:
            symbol: Symbol to get quote for.

        Returns:
            Simulated quote data.
        """
        self._require_connection()

        base_price = self.get_simulated_price(symbol)

        # Simulate bid/ask spread
        spread = base_price * Decimal("0.001")  # 0.1% spread
        bid = base_price - spread / 2
        ask = base_price + spread / 2

        return Quote(
            symbol=symbol,
            bid_price=bid.quantize(Decimal("0.01")),
            ask_price=ask.quantize(Decimal("0.01")),
            last_price=base_price,
            bid_size=random.randint(100, 1000),
            ask_size=random.randint(100, 1000),
            volume=random.randint(100000, 10000000),
            timestamp=datetime.now(timezone.utc),
        )

    async def get_asset(self, symbol: str) -> AssetInfo:
        """Get simulated asset information.

        Args:
            symbol: Symbol to get info for.

        Returns:
            Simulated asset information.
        """
        self._require_connection()

        # Determine asset class based on symbol patterns
        if symbol.endswith("USD"):
            asset_class = AssetClass.CRYPTO
        elif symbol in ["ES", "NQ", "CL", "GC"]:
            asset_class = AssetClass.FUTURE
        elif symbol in ["SPY", "QQQ", "IWM", "VTI"]:
            asset_class = AssetClass.ETF
        else:
            asset_class = AssetClass.EQUITY

        return AssetInfo(
            symbol=symbol,
            name=f"{symbol} (Paper)",
            asset_class=asset_class,
            exchange="PAPER",
            tradable=True,
            shortable=True,
            marginable=True,
            fractionable=False,
        )

    def reset(self) -> None:
        """Reset broker to initial state.

        Clears all positions and orders, resets cash to initial amount.
        """
        self._cash = self._initial_cash
        self._orders.clear()
        self._positions.clear()
        self._order_counter = 0


# Export
__all__ = ["PaperBroker"]
