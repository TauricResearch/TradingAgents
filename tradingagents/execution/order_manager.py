"""Order Manager for order lifecycle management.

Issue #27: [EXEC-26] Order types and manager - market, limit, stop, trailing

This module provides order lifecycle management including validation,
state transitions, and event notifications.

Features:
    - Order validation before submission
    - Order state machine with valid transitions
    - Order tracking and retrieval
    - Event callbacks for order state changes
    - Support for all order types: market, limit, stop, stop_limit, trailing_stop

Example:
    >>> from tradingagents.execution import OrderManager, OrderRequest, OrderSide
    >>>
    >>> manager = OrderManager()
    >>> request = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))
    >>> order = await manager.submit_order(request, broker)
    >>> print(f"Order {order.broker_order_id} status: {order.status}")
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Awaitable

from .broker_base import (
    BrokerBase,
    Order,
    OrderError,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    InvalidOrderError,
)


class OrderEvent(Enum):
    """Order lifecycle events."""

    CREATED = "created"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    PENDING_CANCEL = "pending_cancel"
    CANCELLED = "cancelled"
    REPLACED = "replaced"
    EXPIRED = "expired"
    ERROR = "error"


# Valid state transitions for order state machine
VALID_TRANSITIONS: Dict[OrderStatus, Set[OrderStatus]] = {
    OrderStatus.PENDING_NEW: {
        OrderStatus.NEW,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.NEW: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.PENDING_CANCEL,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
        OrderStatus.REPLACED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.PENDING_CANCEL,
        OrderStatus.CANCELLED,
    },
    OrderStatus.FILLED: set(),  # Terminal state
    OrderStatus.PENDING_CANCEL: {
        OrderStatus.CANCELLED,
        OrderStatus.FILLED,  # Can fill while cancel is pending
        OrderStatus.PARTIALLY_FILLED,
    },
    OrderStatus.CANCELLED: set(),  # Terminal state
    OrderStatus.REJECTED: set(),  # Terminal state
    OrderStatus.EXPIRED: set(),  # Terminal state
    OrderStatus.REPLACED: set(),  # Terminal state
}

# Terminal states (order cannot change after reaching these)
TERMINAL_STATES: Set[OrderStatus] = {
    OrderStatus.FILLED,
    OrderStatus.CANCELLED,
    OrderStatus.REJECTED,
    OrderStatus.EXPIRED,
    OrderStatus.REPLACED,
}

# Open states (order can still be filled or cancelled)
OPEN_STATES: Set[OrderStatus] = {
    OrderStatus.PENDING_NEW,
    OrderStatus.NEW,
    OrderStatus.PARTIALLY_FILLED,
    OrderStatus.PENDING_CANCEL,
}


@dataclass
class OrderValidationResult:
    """Result of order validation.

    Attributes:
        valid: Whether the order is valid
        errors: List of validation error messages
        warnings: List of validation warning messages
    """
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class OrderStateChange:
    """Record of an order state change.

    Attributes:
        order_id: Order identifier
        from_status: Previous status
        to_status: New status
        event: Event that triggered the change
        timestamp: When the change occurred
        metadata: Additional change details
    """
    order_id: str
    from_status: Optional[OrderStatus]
    to_status: OrderStatus
    event: OrderEvent
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


# Callback type for order events
OrderEventCallback = Callable[[Order, OrderEvent, Dict[str, Any]], Awaitable[None]]


class OrderManager:
    """Manages order lifecycle and state transitions.

    The OrderManager provides:
    - Order validation before submission
    - Order state machine with valid transitions
    - Order tracking and retrieval
    - Event callbacks for order state changes
    - Order history and audit trail

    Example:
        >>> manager = OrderManager()
        >>>
        >>> # Register callbacks
        >>> async def on_fill(order, event, metadata):
        ...     print(f"Order {order.broker_order_id} filled!")
        >>> manager.register_callback(OrderEvent.FILLED, on_fill)
        >>>
        >>> # Submit order
        >>> order = await manager.submit_order(request, broker)
    """

    def __init__(
        self,
        max_orders: int = 10000,
        validate_before_submit: bool = True,
    ) -> None:
        """Initialize order manager.

        Args:
            max_orders: Maximum orders to track (oldest removed when exceeded)
            validate_before_submit: Whether to validate orders before submission
        """
        self._orders: Dict[str, Order] = {}
        self._order_history: Dict[str, List[OrderStateChange]] = {}
        self._callbacks: Dict[OrderEvent, List[OrderEventCallback]] = {
            event: [] for event in OrderEvent
        }
        self._max_orders = max_orders
        self._validate_before_submit = validate_before_submit
        self._lock = asyncio.Lock()

    def register_callback(
        self,
        event: OrderEvent,
        callback: OrderEventCallback,
    ) -> None:
        """Register a callback for an order event.

        Args:
            event: Event to listen for
            callback: Async callback function(order, event, metadata)
        """
        self._callbacks[event].append(callback)

    def unregister_callback(
        self,
        event: OrderEvent,
        callback: OrderEventCallback,
    ) -> None:
        """Unregister a callback.

        Args:
            event: Event type
            callback: Callback to remove
        """
        if callback in self._callbacks[event]:
            self._callbacks[event].remove(callback)

    async def _fire_event(
        self,
        order: Order,
        event: OrderEvent,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Fire callbacks for an event.

        Args:
            order: Order that triggered event
            event: Event type
            metadata: Additional event data
        """
        metadata = metadata or {}
        for callback in self._callbacks[event]:
            try:
                await callback(order, event, metadata)
            except Exception:
                # Don't let callback errors break order flow
                pass

    def validate_order(self, request: OrderRequest) -> OrderValidationResult:
        """Validate an order request.

        Args:
            request: Order request to validate

        Returns:
            Validation result with errors/warnings
        """
        result = OrderValidationResult()

        # Validate quantity
        if request.quantity <= 0:
            result.valid = False
            result.errors.append("Quantity must be positive")

        # Validate limit price for limit orders
        if request.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            if request.limit_price is None:
                result.valid = False
                result.errors.append(f"{request.order_type.value} order requires limit_price")
            elif request.limit_price <= 0:
                result.valid = False
                result.errors.append("Limit price must be positive")

        # Validate stop price for stop orders
        if request.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            if request.stop_price is None:
                result.valid = False
                result.errors.append(f"{request.order_type.value} order requires stop_price")
            elif request.stop_price <= 0:
                result.valid = False
                result.errors.append("Stop price must be positive")

        # Validate trailing stop parameters
        if request.order_type == OrderType.TRAILING_STOP:
            if request.trail_amount is None and request.trail_percent is None:
                result.valid = False
                result.errors.append("Trailing stop requires trail_amount or trail_percent")
            if request.trail_amount is not None and request.trail_amount <= 0:
                result.valid = False
                result.errors.append("Trail amount must be positive")
            if request.trail_percent is not None:
                if request.trail_percent <= 0:
                    result.valid = False
                    result.errors.append("Trail percent must be positive")
                elif request.trail_percent > Decimal("50"):
                    result.warnings.append("Trail percent > 50% may execute far from market")

        # Validate symbol
        if not request.symbol or not request.symbol.strip():
            result.valid = False
            result.errors.append("Symbol is required")

        # Warn about FOK/IOC with limit orders far from market
        if request.time_in_force in (TimeInForce.FOK, TimeInForce.IOC):
            if request.order_type == OrderType.MARKET:
                result.warnings.append(
                    f"{request.time_in_force.value} with market order may not execute"
                )

        return result

    def is_valid_transition(
        self,
        from_status: OrderStatus,
        to_status: OrderStatus,
    ) -> bool:
        """Check if a state transition is valid.

        Args:
            from_status: Current status
            to_status: Target status

        Returns:
            True if transition is valid
        """
        return to_status in VALID_TRANSITIONS.get(from_status, set())

    def is_terminal(self, status: OrderStatus) -> bool:
        """Check if a status is terminal.

        Args:
            status: Status to check

        Returns:
            True if status is terminal
        """
        return status in TERMINAL_STATES

    def is_open(self, status: OrderStatus) -> bool:
        """Check if a status means order is open.

        Args:
            status: Status to check

        Returns:
            True if order is open
        """
        return status in OPEN_STATES

    async def submit_order(
        self,
        request: OrderRequest,
        broker: BrokerBase,
    ) -> Order:
        """Submit an order through a broker.

        Args:
            request: Order request
            broker: Broker to submit through

        Returns:
            Submitted order

        Raises:
            InvalidOrderError: If validation fails
            OrderError: If submission fails
        """
        # Validate if enabled
        if self._validate_before_submit:
            validation = self.validate_order(request)
            if not validation.valid:
                raise InvalidOrderError(
                    f"Order validation failed: {'; '.join(validation.errors)}"
                )

        # Submit to broker
        order = await broker.submit_order(request)

        # Track the order
        async with self._lock:
            self._orders[order.broker_order_id] = order
            self._order_history[order.broker_order_id] = [
                OrderStateChange(
                    order_id=order.broker_order_id,
                    from_status=None,
                    to_status=order.status,
                    event=OrderEvent.SUBMITTED,
                )
            ]

            # Trim old orders if at max
            if len(self._orders) > self._max_orders:
                # Remove oldest orders
                sorted_orders = sorted(
                    self._orders.items(),
                    key=lambda x: x[1].created_at or datetime.min,
                )
                for order_id, _ in sorted_orders[: len(self._orders) - self._max_orders]:
                    del self._orders[order_id]
                    self._order_history.pop(order_id, None)

        # Fire event
        await self._fire_event(order, OrderEvent.SUBMITTED)

        # Fire additional events based on status
        if order.status == OrderStatus.FILLED:
            await self._fire_event(order, OrderEvent.FILLED)
        elif order.status == OrderStatus.REJECTED:
            await self._fire_event(order, OrderEvent.REJECTED)

        return order

    async def cancel_order(
        self,
        order_id: str,
        broker: BrokerBase,
    ) -> Order:
        """Cancel an order.

        Args:
            order_id: Order to cancel
            broker: Broker to cancel through

        Returns:
            Cancelled order

        Raises:
            OrderError: If cancel fails
        """
        order = await broker.cancel_order(order_id)

        async with self._lock:
            old_order = self._orders.get(order_id)
            old_status = old_order.status if old_order else None
            self._orders[order_id] = order

            if order_id in self._order_history:
                self._order_history[order_id].append(
                    OrderStateChange(
                        order_id=order_id,
                        from_status=old_status,
                        to_status=order.status,
                        event=OrderEvent.CANCELLED,
                    )
                )

        await self._fire_event(order, OrderEvent.CANCELLED)
        return order

    async def replace_order(
        self,
        order_id: str,
        broker: BrokerBase,
        quantity: Optional[Decimal] = None,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
    ) -> Order:
        """Replace an order with updated parameters.

        Args:
            order_id: Order to replace
            broker: Broker to replace through
            quantity: New quantity
            limit_price: New limit price
            stop_price: New stop price
            time_in_force: New time in force

        Returns:
            New replacement order
        """
        new_order = await broker.replace_order(
            order_id,
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force,
        )

        async with self._lock:
            # Mark old order as replaced
            if order_id in self._orders:
                old_order = self._orders[order_id]
                old_order.status = OrderStatus.REPLACED
                self._order_history[order_id].append(
                    OrderStateChange(
                        order_id=order_id,
                        from_status=old_order.status,
                        to_status=OrderStatus.REPLACED,
                        event=OrderEvent.REPLACED,
                        metadata={"replaced_by": new_order.broker_order_id},
                    )
                )

            # Track new order
            self._orders[new_order.broker_order_id] = new_order
            self._order_history[new_order.broker_order_id] = [
                OrderStateChange(
                    order_id=new_order.broker_order_id,
                    from_status=None,
                    to_status=new_order.status,
                    event=OrderEvent.SUBMITTED,
                    metadata={"replaces": order_id},
                )
            ]

        await self._fire_event(new_order, OrderEvent.REPLACED)
        return new_order

    async def update_order_status(
        self,
        order: Order,
    ) -> None:
        """Update tracked order status.

        Called when order status changes (e.g., from broker callbacks).

        Args:
            order: Order with updated status
        """
        async with self._lock:
            old_order = self._orders.get(order.broker_order_id)
            old_status = old_order.status if old_order else None

            # Validate transition
            if old_status and not self.is_valid_transition(old_status, order.status):
                # Log warning but allow - broker is authoritative
                pass

            self._orders[order.broker_order_id] = order

            # Record state change
            event = self._status_to_event(order.status)
            if order.broker_order_id in self._order_history:
                self._order_history[order.broker_order_id].append(
                    OrderStateChange(
                        order_id=order.broker_order_id,
                        from_status=old_status,
                        to_status=order.status,
                        event=event,
                    )
                )

        await self._fire_event(order, event)

    def _status_to_event(self, status: OrderStatus) -> OrderEvent:
        """Convert order status to event type."""
        mapping = {
            OrderStatus.PENDING_NEW: OrderEvent.SUBMITTED,
            OrderStatus.NEW: OrderEvent.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED: OrderEvent.PARTIALLY_FILLED,
            OrderStatus.FILLED: OrderEvent.FILLED,
            OrderStatus.PENDING_CANCEL: OrderEvent.PENDING_CANCEL,
            OrderStatus.CANCELLED: OrderEvent.CANCELLED,
            OrderStatus.REJECTED: OrderEvent.REJECTED,
            OrderStatus.EXPIRED: OrderEvent.EXPIRED,
            OrderStatus.REPLACED: OrderEvent.REPLACED,
        }
        return mapping.get(status, OrderEvent.ERROR)

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get tracked order by ID.

        Args:
            order_id: Order identifier

        Returns:
            Order if found, None otherwise
        """
        return self._orders.get(order_id)

    def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        symbol: Optional[str] = None,
        side: Optional[OrderSide] = None,
    ) -> List[Order]:
        """Get tracked orders with optional filters.

        Args:
            status: Filter by status
            symbol: Filter by symbol
            side: Filter by side

        Returns:
            List of matching orders
        """
        orders = list(self._orders.values())

        if status:
            orders = [o for o in orders if o.status == status]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        if side:
            orders = [o for o in orders if o.side == side]

        return orders

    def get_open_orders(self) -> List[Order]:
        """Get all open (non-terminal) orders.

        Returns:
            List of open orders
        """
        return [o for o in self._orders.values() if self.is_open(o.status)]

    def get_order_history(self, order_id: str) -> List[OrderStateChange]:
        """Get state change history for an order.

        Args:
            order_id: Order identifier

        Returns:
            List of state changes
        """
        return self._order_history.get(order_id, [])

    def clear_completed_orders(self) -> int:
        """Remove all terminal (completed) orders from tracking.

        Returns:
            Number of orders removed
        """
        to_remove = [
            order_id
            for order_id, order in self._orders.items()
            if self.is_terminal(order.status)
        ]

        for order_id in to_remove:
            del self._orders[order_id]
            self._order_history.pop(order_id, None)

        return len(to_remove)

    @property
    def order_count(self) -> int:
        """Get number of tracked orders."""
        return len(self._orders)

    @property
    def open_order_count(self) -> int:
        """Get number of open orders."""
        return len(self.get_open_orders())


# Export
__all__ = [
    "OrderManager",
    "OrderEvent",
    "OrderValidationResult",
    "OrderStateChange",
    "OrderEventCallback",
    "VALID_TRANSITIONS",
    "TERMINAL_STATES",
    "OPEN_STATES",
]
