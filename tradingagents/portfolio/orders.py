"""
Order management for the portfolio system.

This module provides various order types for executing trades, including
market orders, limit orders, stop-loss orders, and take-profit orders.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any
import logging

from tradingagents.security import validate_ticker
from .exceptions import (
    InvalidOrderError,
    InvalidPriceError,
    InvalidQuantityError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Enumeration of order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class OrderSide(Enum):
    """Enumeration of order sides."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Enumeration of order statuses."""
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PARTIALLY_FILLED = "partially_filled"


@dataclass
class Order:
    """
    Base class for all order types.

    Attributes:
        ticker: The security ticker symbol
        quantity: Number of shares to trade (positive for buy, negative for sell)
        order_type: Type of order
        created_at: Timestamp when order was created
        status: Current status of the order
        filled_quantity: Quantity that has been filled
        filled_price: Average price of filled quantity
        executed_at: Timestamp when order was executed (if applicable)
        metadata: Optional additional metadata
    """

    ticker: str
    quantity: Decimal
    order_type: OrderType
    created_at: datetime = field(default_factory=datetime.now)
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal('0')
    filled_price: Optional[Decimal] = None
    executed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate order data after initialization."""
        # Validate ticker
        try:
            self.ticker = validate_ticker(self.ticker)
        except ValueError as e:
            raise InvalidOrderError(f"Invalid ticker: {e}")

        # Convert to Decimal if needed
        if not isinstance(self.quantity, Decimal):
            try:
                self.quantity = Decimal(str(self.quantity))
            except (ValueError, TypeError) as e:
                raise InvalidQuantityError(f"Invalid quantity: {e}")

        # Validate quantity is not zero
        if self.quantity == 0:
            raise InvalidQuantityError("Order quantity cannot be zero")

        logger.info(
            f"Created {self.order_type.value} order: {self.ticker} "
            f"quantity={self.quantity} status={self.status.value}"
        )

    @property
    def is_buy(self) -> bool:
        """Check if this is a buy order."""
        return self.quantity > 0

    @property
    def is_sell(self) -> bool:
        """Check if this is a sell order."""
        return self.quantity < 0

    @property
    def side(self) -> OrderSide:
        """Get the order side (buy or sell)."""
        return OrderSide.BUY if self.is_buy else OrderSide.SELL

    @property
    def is_filled(self) -> bool:
        """Check if the order is fully filled."""
        return self.filled_quantity == abs(self.quantity)

    @property
    def is_partially_filled(self) -> bool:
        """Check if the order is partially filled."""
        return Decimal('0') < self.filled_quantity < abs(self.quantity)

    def mark_executed(
        self,
        filled_quantity: Decimal,
        filled_price: Decimal,
        execution_time: Optional[datetime] = None
    ) -> None:
        """
        Mark the order as executed.

        Args:
            filled_quantity: Quantity that was filled
            filled_price: Price at which the order was filled
            execution_time: Time of execution (defaults to now)

        Raises:
            InvalidOrderError: If the order cannot be executed
            InvalidQuantityError: If filled_quantity is invalid
            InvalidPriceError: If filled_price is invalid
        """
        if self.status == OrderStatus.EXECUTED:
            raise InvalidOrderError("Order already executed")

        if self.status == OrderStatus.CANCELLED:
            raise InvalidOrderError("Cannot execute cancelled order")

        if not isinstance(filled_quantity, Decimal):
            try:
                filled_quantity = Decimal(str(filled_quantity))
            except (ValueError, TypeError) as e:
                raise InvalidQuantityError(f"Invalid filled quantity: {e}")

        if not isinstance(filled_price, Decimal):
            try:
                filled_price = Decimal(str(filled_price))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid filled price: {e}")

        if filled_quantity <= 0:
            raise InvalidQuantityError("Filled quantity must be positive")

        if filled_price <= 0:
            raise InvalidPriceError("Filled price must be positive")

        if filled_quantity > abs(self.quantity):
            raise InvalidQuantityError(
                f"Filled quantity {filled_quantity} exceeds order quantity {abs(self.quantity)}"
            )

        self.filled_quantity = filled_quantity
        self.filled_price = filled_price
        self.executed_at = execution_time or datetime.now()

        if self.is_filled:
            self.status = OrderStatus.EXECUTED
        else:
            self.status = OrderStatus.PARTIALLY_FILLED

        logger.info(
            f"Executed order: {self.ticker} "
            f"filled_qty={filled_quantity} price={filled_price} "
            f"status={self.status.value}"
        )

    def cancel(self) -> None:
        """
        Cancel the order.

        Raises:
            InvalidOrderError: If the order cannot be cancelled
        """
        if self.status == OrderStatus.EXECUTED:
            raise InvalidOrderError("Cannot cancel executed order")

        if self.status == OrderStatus.CANCELLED:
            raise InvalidOrderError("Order already cancelled")

        self.status = OrderStatus.CANCELLED
        logger.info(f"Cancelled order: {self.ticker} quantity={self.quantity}")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert order to dictionary for serialization.

        Returns:
            Dictionary representation of the order
        """
        return {
            'ticker': self.ticker,
            'quantity': str(self.quantity),
            'order_type': self.order_type.value,
            'created_at': self.created_at.isoformat(),
            'status': self.status.value,
            'filled_quantity': str(self.filled_quantity),
            'filled_price': str(self.filled_price) if self.filled_price else None,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
            'metadata': self.metadata,
        }

    def __repr__(self) -> str:
        """String representation of the order."""
        side = "BUY" if self.is_buy else "SELL"
        return (
            f"Order({self.order_type.value.upper()}, {side}, {self.ticker}, "
            f"qty={abs(self.quantity)}, status={self.status.value})"
        )


@dataclass
class MarketOrder(Order):
    """
    Market order that executes immediately at the current market price.

    A market order is guaranteed to execute (assuming sufficient liquidity)
    but the price is not guaranteed.

    Example:
        >>> order = MarketOrder('AAPL', Decimal('100'))  # Buy 100 shares at market
        >>> order = MarketOrder('AAPL', Decimal('-50'))  # Sell 50 shares at market
    """

    order_type: OrderType = field(default=OrderType.MARKET, init=False)

    def can_execute(self, current_price: Decimal) -> bool:
        """
        Check if the order can be executed at the current price.

        Market orders can always be executed.

        Args:
            current_price: Current market price

        Returns:
            Always True for market orders
        """
        return True


@dataclass
class LimitOrder(Order):
    """
    Limit order that only executes at a specified price or better.

    For buy orders: executes at limit_price or lower
    For sell orders: executes at limit_price or higher

    Attributes:
        limit_price: The price limit for the order

    Example:
        >>> order = LimitOrder('AAPL', Decimal('100'), limit_price=Decimal('150.00'))
        >>> # Buy 100 shares only if price is <= $150.00
    """

    limit_price: Decimal = None
    order_type: OrderType = field(default=OrderType.LIMIT, init=False)

    def __post_init__(self):
        """Validate limit order data."""
        super().__post_init__()

        if self.limit_price is None:
            raise InvalidOrderError("Limit price is required for limit orders")

        if not isinstance(self.limit_price, Decimal):
            try:
                self.limit_price = Decimal(str(self.limit_price))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid limit price: {e}")

        if self.limit_price <= 0:
            raise InvalidPriceError("Limit price must be positive")

    def can_execute(self, current_price: Decimal) -> bool:
        """
        Check if the order can be executed at the current price.

        Args:
            current_price: Current market price

        Returns:
            True if the order can be executed at current price

        Raises:
            InvalidPriceError: If current_price is invalid
        """
        if not isinstance(current_price, Decimal):
            try:
                current_price = Decimal(str(current_price))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid current price: {e}")

        if current_price <= 0:
            raise InvalidPriceError("Current price must be positive")

        if self.is_buy:
            # Buy order executes if current price is at or below limit
            return current_price <= self.limit_price
        else:
            # Sell order executes if current price is at or above limit
            return current_price >= self.limit_price

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with limit price."""
        data = super().to_dict()
        data['limit_price'] = str(self.limit_price)
        return data


@dataclass
class StopLossOrder(Order):
    """
    Stop-loss order that triggers when price reaches a specified level.

    Used to limit losses by automatically closing a position when
    the price moves against you.

    For long positions: triggers when price falls to or below stop_price
    For short positions: triggers when price rises to or above stop_price

    Attributes:
        stop_price: The price at which the order triggers

    Example:
        >>> order = StopLossOrder('AAPL', Decimal('-100'), stop_price=Decimal('145.00'))
        >>> # Sell 100 shares if price drops to or below $145.00
    """

    stop_price: Decimal = None
    order_type: OrderType = field(default=OrderType.STOP_LOSS, init=False)

    def __post_init__(self):
        """Validate stop-loss order data."""
        super().__post_init__()

        if self.stop_price is None:
            raise InvalidOrderError("Stop price is required for stop-loss orders")

        if not isinstance(self.stop_price, Decimal):
            try:
                self.stop_price = Decimal(str(self.stop_price))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid stop price: {e}")

        if self.stop_price <= 0:
            raise InvalidPriceError("Stop price must be positive")

    def can_execute(self, current_price: Decimal) -> bool:
        """
        Check if the stop-loss should be triggered.

        Args:
            current_price: Current market price

        Returns:
            True if stop-loss should trigger

        Raises:
            InvalidPriceError: If current_price is invalid
        """
        if not isinstance(current_price, Decimal):
            try:
                current_price = Decimal(str(current_price))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid current price: {e}")

        if current_price <= 0:
            raise InvalidPriceError("Current price must be positive")

        # Stop-loss for closing long positions (sell order)
        if self.is_sell:
            return current_price <= self.stop_price
        # Stop-loss for closing short positions (buy order)
        else:
            return current_price >= self.stop_price

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with stop price."""
        data = super().to_dict()
        data['stop_price'] = str(self.stop_price)
        return data


@dataclass
class TakeProfitOrder(Order):
    """
    Take-profit order that triggers when price reaches a profit target.

    Used to lock in profits by automatically closing a position when
    the price reaches a favorable level.

    For long positions: triggers when price rises to or above target_price
    For short positions: triggers when price falls to or below target_price

    Attributes:
        target_price: The price at which the order triggers

    Example:
        >>> order = TakeProfitOrder('AAPL', Decimal('-100'), target_price=Decimal('160.00'))
        >>> # Sell 100 shares if price rises to or above $160.00
    """

    target_price: Decimal = None
    order_type: OrderType = field(default=OrderType.TAKE_PROFIT, init=False)

    def __post_init__(self):
        """Validate take-profit order data."""
        super().__post_init__()

        if self.target_price is None:
            raise InvalidOrderError("Target price is required for take-profit orders")

        if not isinstance(self.target_price, Decimal):
            try:
                self.target_price = Decimal(str(self.target_price))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid target price: {e}")

        if self.target_price <= 0:
            raise InvalidPriceError("Target price must be positive")

    def can_execute(self, current_price: Decimal) -> bool:
        """
        Check if the take-profit should be triggered.

        Args:
            current_price: Current market price

        Returns:
            True if take-profit should trigger

        Raises:
            InvalidPriceError: If current_price is invalid
        """
        if not isinstance(current_price, Decimal):
            try:
                current_price = Decimal(str(current_price))
            except (ValueError, TypeError) as e:
                raise InvalidPriceError(f"Invalid current price: {e}")

        if current_price <= 0:
            raise InvalidPriceError("Current price must be positive")

        # Take-profit for closing long positions (sell order)
        if self.is_sell:
            return current_price >= self.target_price
        # Take-profit for closing short positions (buy order)
        else:
            return current_price <= self.target_price

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with target price."""
        data = super().to_dict()
        data['target_price'] = str(self.target_price)
        return data


def create_order_from_dict(data: Dict[str, Any]) -> Order:
    """
    Create an order from a dictionary.

    Args:
        data: Dictionary containing order data

    Returns:
        Order instance of the appropriate type

    Raises:
        ValidationError: If data is invalid
    """
    try:
        order_type = OrderType(data['order_type'])
        base_args = {
            'ticker': data['ticker'],
            'quantity': Decimal(data['quantity']),
            'created_at': datetime.fromisoformat(data['created_at']),
            'status': OrderStatus(data['status']),
            'filled_quantity': Decimal(data['filled_quantity']),
            'filled_price': Decimal(data['filled_price']) if data.get('filled_price') else None,
            'executed_at': datetime.fromisoformat(data['executed_at']) if data.get('executed_at') else None,
            'metadata': data.get('metadata', {}),
        }

        if order_type == OrderType.MARKET:
            return MarketOrder(**base_args)
        elif order_type == OrderType.LIMIT:
            base_args['limit_price'] = Decimal(data['limit_price'])
            return LimitOrder(**base_args)
        elif order_type == OrderType.STOP_LOSS:
            base_args['stop_price'] = Decimal(data['stop_price'])
            return StopLossOrder(**base_args)
        elif order_type == OrderType.TAKE_PROFIT:
            base_args['target_price'] = Decimal(data['target_price'])
            return TakeProfitOrder(**base_args)
        else:
            raise ValidationError(f"Unknown order type: {order_type}")

    except (KeyError, ValueError, TypeError) as e:
        raise ValidationError(f"Invalid order data: {e}")
