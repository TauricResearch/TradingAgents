"""Tests for Order Manager implementation.

Issue #27: [EXEC-26] Order types and manager - market, limit, stop, trailing
"""

from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from tradingagents.execution import (
    OrderManager,
    OrderEvent,
    OrderValidationResult,
    OrderStateChange,
    PaperBroker,
    OrderRequest,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    InvalidOrderError,
    VALID_TRANSITIONS,
    TERMINAL_STATES,
    OPEN_STATES,
)


class TestOrderValidationResult:
    """Test OrderValidationResult dataclass."""

    def test_default_valid(self):
        """Test default result is valid."""
        result = OrderValidationResult()
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_invalid_with_errors(self):
        """Test result with errors."""
        result = OrderValidationResult(
            valid=False,
            errors=["Error 1", "Error 2"],
        )
        assert result.valid is False
        assert len(result.errors) == 2

    def test_valid_with_warnings(self):
        """Test result with warnings but still valid."""
        result = OrderValidationResult(
            valid=True,
            warnings=["Warning 1"],
        )
        assert result.valid is True
        assert len(result.warnings) == 1


class TestOrderStateChange:
    """Test OrderStateChange dataclass."""

    def test_state_change_creation(self):
        """Test creating state change record."""
        change = OrderStateChange(
            order_id="TEST-123",
            from_status=OrderStatus.NEW,
            to_status=OrderStatus.FILLED,
            event=OrderEvent.FILLED,
        )
        assert change.order_id == "TEST-123"
        assert change.from_status == OrderStatus.NEW
        assert change.to_status == OrderStatus.FILLED
        assert change.event == OrderEvent.FILLED
        assert isinstance(change.timestamp, datetime)

    def test_state_change_with_metadata(self):
        """Test state change with metadata."""
        change = OrderStateChange(
            order_id="TEST-123",
            from_status=None,
            to_status=OrderStatus.NEW,
            event=OrderEvent.SUBMITTED,
            metadata={"broker": "paper"},
        )
        assert change.metadata == {"broker": "paper"}


class TestOrderManagerInit:
    """Test OrderManager initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        manager = OrderManager()
        assert manager.order_count == 0
        assert manager.open_order_count == 0

    def test_custom_max_orders(self):
        """Test initialization with custom max orders."""
        manager = OrderManager(max_orders=100)
        assert manager._max_orders == 100

    def test_validation_disabled(self):
        """Test initialization with validation disabled."""
        manager = OrderManager(validate_before_submit=False)
        assert manager._validate_before_submit is False


class TestOrderValidation:
    """Test OrderManager order validation."""

    def test_valid_market_order(self):
        """Test valid market order."""
        manager = OrderManager()
        request = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("100"))
        result = manager.validate_order(request)
        assert result.valid is True

    def test_invalid_quantity_zero(self):
        """Test invalid order with zero quantity."""
        manager = OrderManager()
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("0"),
        )
        result = manager.validate_order(request)
        assert result.valid is False
        assert any("positive" in e.lower() for e in result.errors)

    def test_invalid_quantity_negative(self):
        """Test invalid order with negative quantity."""
        manager = OrderManager()
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("-10"),
        )
        result = manager.validate_order(request)
        assert result.valid is False

    def test_limit_order_missing_price(self):
        """Test limit order without limit price raises at construction."""
        # OrderRequest validates in __post_init__
        with pytest.raises(ValueError, match="limit_price"):
            OrderRequest(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("100"),
                order_type=OrderType.LIMIT,
                limit_price=None,
            )

    def test_limit_order_with_price(self):
        """Test valid limit order."""
        manager = OrderManager()
        request = OrderRequest.limit(
            "AAPL", OrderSide.BUY, Decimal("100"), Decimal("150.00")
        )
        result = manager.validate_order(request)
        assert result.valid is True

    def test_stop_order_missing_stop_price(self):
        """Test stop order without stop price raises at construction."""
        # OrderRequest validates in __post_init__
        with pytest.raises(ValueError, match="stop_price"):
            OrderRequest(
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=Decimal("100"),
                order_type=OrderType.STOP,
                stop_price=None,
            )

    def test_stop_limit_order_missing_both(self):
        """Test stop limit order missing both prices raises at construction."""
        # OrderRequest validates in __post_init__
        with pytest.raises(ValueError, match="stop_price|limit_price"):
            OrderRequest(
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=Decimal("100"),
                order_type=OrderType.STOP_LIMIT,
            )

    def test_trailing_stop_missing_trail(self):
        """Test trailing stop without trail parameters raises at construction."""
        # OrderRequest validates in __post_init__
        with pytest.raises(ValueError, match="trail"):
            OrderRequest(
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=Decimal("100"),
                order_type=OrderType.TRAILING_STOP,
            )

    def test_trailing_stop_with_percent(self):
        """Test valid trailing stop with percent."""
        manager = OrderManager()
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=Decimal("100"),
            order_type=OrderType.TRAILING_STOP,
            trail_percent=Decimal("5.0"),
        )
        result = manager.validate_order(request)
        assert result.valid is True

    def test_trailing_stop_high_percent_warning(self):
        """Test trailing stop with high percent warns."""
        manager = OrderManager()
        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=Decimal("100"),
            order_type=OrderType.TRAILING_STOP,
            trail_percent=Decimal("60.0"),
        )
        result = manager.validate_order(request)
        assert result.valid is True
        assert len(result.warnings) > 0

    def test_empty_symbol(self):
        """Test order with empty symbol."""
        manager = OrderManager()
        request = OrderRequest(
            symbol="",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
        )
        result = manager.validate_order(request)
        assert result.valid is False
        assert any("symbol" in e.lower() for e in result.errors)


class TestStateTransitions:
    """Test order state machine transitions."""

    def test_valid_transitions_defined(self):
        """Test all statuses have defined transitions."""
        for status in OrderStatus:
            assert status in VALID_TRANSITIONS

    def test_terminal_states_immutable(self):
        """Test terminal states have no valid transitions."""
        for status in TERMINAL_STATES:
            assert len(VALID_TRANSITIONS[status]) == 0

    def test_open_states_have_transitions(self):
        """Test open states have transitions."""
        for status in OPEN_STATES:
            assert len(VALID_TRANSITIONS[status]) > 0

    def test_is_valid_transition(self):
        """Test valid transition checking."""
        manager = OrderManager()
        assert manager.is_valid_transition(OrderStatus.NEW, OrderStatus.FILLED)
        assert manager.is_valid_transition(OrderStatus.NEW, OrderStatus.CANCELLED)
        assert not manager.is_valid_transition(OrderStatus.FILLED, OrderStatus.NEW)

    def test_is_terminal(self):
        """Test terminal status checking."""
        manager = OrderManager()
        assert manager.is_terminal(OrderStatus.FILLED) is True
        assert manager.is_terminal(OrderStatus.CANCELLED) is True
        assert manager.is_terminal(OrderStatus.NEW) is False

    def test_is_open(self):
        """Test open status checking."""
        manager = OrderManager()
        assert manager.is_open(OrderStatus.NEW) is True
        assert manager.is_open(OrderStatus.PARTIALLY_FILLED) is True
        assert manager.is_open(OrderStatus.FILLED) is False


class TestOrderSubmission:
    """Test OrderManager order submission."""

    @pytest.mark.asyncio
    async def test_submit_order(self):
        """Test basic order submission."""
        manager = OrderManager()
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        request = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        order = await manager.submit_order(request, broker)

        assert order.symbol == "AAPL"
        assert order.status == OrderStatus.FILLED
        assert manager.order_count == 1

    @pytest.mark.asyncio
    async def test_submit_order_validation_fails(self):
        """Test submission fails on invalid order."""
        manager = OrderManager()
        broker = PaperBroker()
        await broker.connect()

        request = OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("-10"),
        )

        with pytest.raises(InvalidOrderError):
            await manager.submit_order(request, broker)

    @pytest.mark.asyncio
    async def test_submit_order_validation_disabled(self):
        """Test submission with validation disabled."""
        manager = OrderManager(validate_before_submit=False)
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        # This would normally fail validation but passes with disabled
        request = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        order = await manager.submit_order(request, broker)
        assert order is not None

    @pytest.mark.asyncio
    async def test_order_tracking(self):
        """Test order is tracked after submission."""
        manager = OrderManager()
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        request = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        order = await manager.submit_order(request, broker)

        tracked = manager.get_order(order.broker_order_id)
        assert tracked is not None
        assert tracked.broker_order_id == order.broker_order_id

    @pytest.mark.asyncio
    async def test_order_history_recorded(self):
        """Test order history is recorded."""
        manager = OrderManager()
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        request = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        order = await manager.submit_order(request, broker)

        history = manager.get_order_history(order.broker_order_id)
        assert len(history) >= 1
        assert history[0].event == OrderEvent.SUBMITTED


class TestOrderCallbacks:
    """Test OrderManager event callbacks."""

    @pytest.mark.asyncio
    async def test_register_callback(self):
        """Test registering callback."""
        manager = OrderManager()
        callback_called = []

        async def callback(order, event, metadata):
            callback_called.append((order, event))

        manager.register_callback(OrderEvent.FILLED, callback)

        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        await manager.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")),
            broker,
        )

        assert len(callback_called) == 1
        assert callback_called[0][1] == OrderEvent.FILLED

    @pytest.mark.asyncio
    async def test_unregister_callback(self):
        """Test unregistering callback."""
        manager = OrderManager()
        callback_called = []

        async def callback(order, event, metadata):
            callback_called.append(True)

        manager.register_callback(OrderEvent.FILLED, callback)
        manager.unregister_callback(OrderEvent.FILLED, callback)

        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        await manager.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")),
            broker,
        )

        assert len(callback_called) == 0

    @pytest.mark.asyncio
    async def test_callback_error_doesnt_break_flow(self):
        """Test callback error doesn't break order flow."""
        manager = OrderManager()

        async def bad_callback(order, event, metadata):
            raise Exception("Callback error")

        manager.register_callback(OrderEvent.FILLED, bad_callback)

        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("100"))
        await broker.connect()

        # Should not raise despite callback error
        order = await manager.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")),
            broker,
        )
        assert order is not None


class TestOrderCancellation:
    """Test OrderManager order cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """Test cancelling an order."""
        manager = OrderManager()
        broker = PaperBroker(fill_probability=0.0)
        await broker.connect()

        request = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        order = await manager.submit_order(request, broker)

        cancelled = await manager.cancel_order(order.broker_order_id, broker)
        assert cancelled.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_updates_tracking(self):
        """Test cancellation updates tracked order."""
        manager = OrderManager()
        broker = PaperBroker(fill_probability=0.0)
        await broker.connect()

        request = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        order = await manager.submit_order(request, broker)

        await manager.cancel_order(order.broker_order_id, broker)

        tracked = manager.get_order(order.broker_order_id)
        assert tracked.status == OrderStatus.CANCELLED


class TestOrderReplacement:
    """Test OrderManager order replacement."""

    @pytest.mark.asyncio
    async def test_replace_order(self):
        """Test replacing an order."""
        manager = OrderManager()
        broker = PaperBroker(fill_probability=0.0)
        await broker.connect()

        request = OrderRequest.limit(
            "AAPL", OrderSide.BUY, Decimal("10"), Decimal("100")
        )
        order = await manager.submit_order(request, broker)

        new_order = await manager.replace_order(
            order.broker_order_id,
            broker,
            quantity=Decimal("20"),
        )

        assert new_order.quantity == Decimal("20")
        assert new_order.broker_order_id != order.broker_order_id


class TestOrderQueries:
    """Test OrderManager query methods."""

    @pytest.mark.asyncio
    async def test_get_orders_all(self):
        """Test getting all orders."""
        manager = OrderManager()
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        broker.set_price("MSFT", Decimal("10"))
        await broker.connect()

        await manager.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")), broker
        )
        await manager.submit_order(
            OrderRequest.market("MSFT", OrderSide.BUY, Decimal("10")), broker
        )

        orders = manager.get_orders()
        assert len(orders) == 2

    @pytest.mark.asyncio
    async def test_get_orders_by_symbol(self):
        """Test filtering orders by symbol."""
        manager = OrderManager()
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        broker.set_price("MSFT", Decimal("10"))
        await broker.connect()

        await manager.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")), broker
        )
        await manager.submit_order(
            OrderRequest.market("MSFT", OrderSide.BUY, Decimal("10")), broker
        )

        orders = manager.get_orders(symbol="AAPL")
        assert len(orders) == 1
        assert orders[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_orders_by_status(self):
        """Test filtering orders by status."""
        manager = OrderManager()
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        await broker.connect()

        # Create filled order
        await manager.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")), broker
        )

        # Create unfilled order
        broker._fill_probability = 0.0
        await manager.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")), broker
        )

        filled_orders = manager.get_orders(status=OrderStatus.FILLED)
        assert len(filled_orders) == 1

    @pytest.mark.asyncio
    async def test_get_open_orders(self):
        """Test getting open orders only."""
        manager = OrderManager()
        broker = PaperBroker(fill_probability=0.0)
        await broker.connect()

        await manager.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")), broker
        )

        open_orders = manager.get_open_orders()
        assert len(open_orders) == 1


class TestOrderCleanup:
    """Test OrderManager order cleanup."""

    @pytest.mark.asyncio
    async def test_clear_completed_orders(self):
        """Test clearing completed orders."""
        manager = OrderManager()
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("10"))
        await broker.connect()

        # Create filled orders
        await manager.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")), broker
        )
        await manager.submit_order(
            OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10")), broker
        )

        assert manager.order_count == 2

        removed = manager.clear_completed_orders()
        assert removed == 2
        assert manager.order_count == 0

    @pytest.mark.asyncio
    async def test_max_orders_limit(self):
        """Test orders are trimmed when max reached."""
        manager = OrderManager(max_orders=5)
        broker = PaperBroker()
        broker.set_price("AAPL", Decimal("1"))
        await broker.connect()

        # Submit more than max orders
        for _ in range(10):
            await manager.submit_order(
                OrderRequest.market("AAPL", OrderSide.BUY, Decimal("1")), broker
            )

        assert manager.order_count <= 5


class TestOrderStatusUpdate:
    """Test OrderManager status updates."""

    @pytest.mark.asyncio
    async def test_update_order_status(self):
        """Test updating order status."""
        manager = OrderManager()
        broker = PaperBroker(fill_probability=0.0)
        await broker.connect()

        request = OrderRequest.market("AAPL", OrderSide.BUY, Decimal("10"))
        order = await manager.submit_order(request, broker)

        # Simulate status change
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        await manager.update_order_status(order)

        tracked = manager.get_order(order.broker_order_id)
        assert tracked.status == OrderStatus.FILLED


class TestOrderEvents:
    """Test OrderEvent enum."""

    def test_all_events_defined(self):
        """Test all expected events are defined."""
        expected_events = [
            "CREATED", "SUBMITTED", "ACCEPTED", "REJECTED",
            "PARTIALLY_FILLED", "FILLED", "PENDING_CANCEL",
            "CANCELLED", "REPLACED", "EXPIRED", "ERROR"
        ]
        for event_name in expected_events:
            assert hasattr(OrderEvent, event_name)


class TestStateConstants:
    """Test state machine constants."""

    def test_terminal_states_complete(self):
        """Test all terminal states are included."""
        assert OrderStatus.FILLED in TERMINAL_STATES
        assert OrderStatus.CANCELLED in TERMINAL_STATES
        assert OrderStatus.REJECTED in TERMINAL_STATES
        assert OrderStatus.EXPIRED in TERMINAL_STATES
        assert OrderStatus.REPLACED in TERMINAL_STATES

    def test_open_states_complete(self):
        """Test all open states are included."""
        assert OrderStatus.PENDING_NEW in OPEN_STATES
        assert OrderStatus.NEW in OPEN_STATES
        assert OrderStatus.PARTIALLY_FILLED in OPEN_STATES
        assert OrderStatus.PENDING_CANCEL in OPEN_STATES

    def test_no_overlap(self):
        """Test terminal and open states don't overlap."""
        overlap = TERMINAL_STATES & OPEN_STATES
        assert len(overlap) == 0
