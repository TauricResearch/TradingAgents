"""Strategy Executor for end-to-end orchestration.

This module provides complete strategy execution including:
- Signal generation to order conversion
- Order submission and execution
- Position and portfolio management
- Error handling with retries
- Comprehensive logging and monitoring

Issue #37: [STRAT-36] Strategy executor - end-to-end orchestration

Design Principles:
    - Full trade lifecycle management
    - Robust error handling with retries
    - Comprehensive logging
    - Event-driven architecture
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple
import asyncio
import logging
import time
import uuid

from tradingagents.strategy.signal_to_order import (
    SignalToOrderConverter,
    TradingSignal,
    SignalType,
    ConversionConfig,
    ConversionResult,
)
from tradingagents.execution.broker_base import (
    OrderRequest,
    OrderSide,
    Order,
    OrderStatus,
)


# ============================================================================
# Logging Setup
# ============================================================================

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class ExecutionStatus(str, Enum):
    """Status of strategy execution."""
    PENDING = "pending"          # Not started
    CONVERTING = "converting"    # Converting signals to orders
    SUBMITTING = "submitting"    # Submitting orders
    EXECUTING = "executing"      # Orders executing
    MONITORING = "monitoring"    # Monitoring positions
    COMPLETED = "completed"      # Execution complete
    FAILED = "failed"            # Execution failed
    CANCELLED = "cancelled"      # Execution cancelled


class RetryPolicy(str, Enum):
    """Retry policy for failed operations."""
    NONE = "none"                # No retries
    IMMEDIATE = "immediate"       # Retry immediately
    EXPONENTIAL = "exponential"  # Exponential backoff
    FIXED = "fixed"              # Fixed delay


class ExecutionEvent(str, Enum):
    """Events during execution."""
    STARTED = "started"
    SIGNAL_RECEIVED = "signal_received"
    ORDER_CREATED = "order_created"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    ORDER_CANCELLED = "order_cancelled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    STOP_TRIGGERED = "stop_triggered"
    TARGET_REACHED = "target_reached"
    ERROR = "error"
    RETRY = "retry"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# Protocols
# ============================================================================

class SignalProvider(Protocol):
    """Protocol for signal generation."""

    def get_signals(self, symbols: List[str]) -> List[TradingSignal]:
        """Generate trading signals for symbols.

        Args:
            symbols: List of symbols to analyze

        Returns:
            List of trading signals
        """
        ...


class OrderExecutor(Protocol):
    """Protocol for order execution."""

    async def submit_order(self, order: OrderRequest) -> Order:
        """Submit an order for execution.

        Args:
            order: Order request to submit

        Returns:
            Submitted order with ID
        """
        ...

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order.

        Args:
            order_id: ID of order to cancel

        Returns:
            True if cancelled successfully
        """
        ...

    async def get_order_status(self, order_id: str) -> Order:
        """Get current order status.

        Args:
            order_id: ID of order to check

        Returns:
            Order with current status
        """
        ...


class PositionManager(Protocol):
    """Protocol for position management."""

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current position for symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position data or None
        """
        ...

    def update_position(
        self,
        symbol: str,
        quantity: Decimal,
        avg_price: Decimal,
    ) -> None:
        """Update position after fill.

        Args:
            symbol: Trading symbol
            quantity: Filled quantity
            avg_price: Average fill price
        """
        ...


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        policy: Retry policy to use
        max_retries: Maximum retry attempts
        initial_delay_ms: Initial delay in milliseconds
        max_delay_ms: Maximum delay in milliseconds
        backoff_multiplier: Multiplier for exponential backoff
    """
    policy: RetryPolicy = RetryPolicy.EXPONENTIAL
    max_retries: int = 3
    initial_delay_ms: int = 100
    max_delay_ms: int = 5000
    backoff_multiplier: float = 2.0


@dataclass
class MonitoringConfig:
    """Configuration for execution monitoring.

    Attributes:
        log_all_events: Log all execution events
        log_level: Default logging level
        track_latency: Track order latency
        track_fills: Track fill quality
        alert_on_failure: Alert on execution failure
        metrics_interval_seconds: Interval for metrics collection
    """
    log_all_events: bool = True
    log_level: str = "INFO"
    track_latency: bool = True
    track_fills: bool = True
    alert_on_failure: bool = True
    metrics_interval_seconds: int = 60


@dataclass
class ExecutorConfig:
    """Configuration for strategy executor.

    Attributes:
        conversion_config: Signal to order conversion config
        retry_config: Retry behavior config
        monitoring_config: Monitoring and logging config
        max_concurrent_orders: Maximum concurrent orders
        order_timeout_seconds: Order fill timeout
        enable_stop_orders: Submit stop loss orders
        enable_take_profit: Submit take profit orders
        dry_run: Simulate without actual execution
    """
    conversion_config: ConversionConfig = field(default_factory=ConversionConfig)
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    monitoring_config: MonitoringConfig = field(default_factory=MonitoringConfig)
    max_concurrent_orders: int = 10
    order_timeout_seconds: int = 300
    enable_stop_orders: bool = True
    enable_take_profit: bool = True
    dry_run: bool = False


@dataclass
class ExecutionEvent_:
    """An event during strategy execution.

    Attributes:
        event_id: Unique event identifier
        event_type: Type of event
        timestamp: When event occurred
        signal_id: Associated signal ID
        order_id: Associated order ID
        symbol: Trading symbol
        message: Event message
        data: Additional event data
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: ExecutionEvent = ExecutionEvent.STARTED
    timestamp: datetime = field(default_factory=datetime.now)
    signal_id: Optional[str] = None
    order_id: Optional[str] = None
    symbol: str = ""
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderExecution:
    """Record of a single order execution.

    Attributes:
        execution_id: Unique execution identifier
        signal: Original signal
        conversion_result: Signal conversion result
        order_request: Generated order request
        submitted_order: Order after submission
        final_status: Final order status
        fill_price: Average fill price
        fill_quantity: Filled quantity
        submit_time: When order was submitted
        fill_time: When order was filled
        latency_ms: Total latency in milliseconds
        retries: Number of retries used
        error_message: Error if failed
    """
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    signal: Optional[TradingSignal] = None
    conversion_result: Optional[ConversionResult] = None
    order_request: Optional[OrderRequest] = None
    submitted_order: Optional[Order] = None
    final_status: OrderStatus = OrderStatus.PENDING_NEW
    fill_price: Optional[Decimal] = None
    fill_quantity: Optional[Decimal] = None
    submit_time: Optional[datetime] = None
    fill_time: Optional[datetime] = None
    latency_ms: Optional[int] = None
    retries: int = 0
    error_message: str = ""


@dataclass
class ExecutionResult:
    """Result of strategy execution.

    Attributes:
        result_id: Unique result identifier
        status: Final execution status
        start_time: Execution start time
        end_time: Execution end time
        total_signals: Number of signals processed
        orders_submitted: Number of orders submitted
        orders_filled: Number of orders filled
        orders_rejected: Number of orders rejected
        orders_cancelled: Number of orders cancelled
        total_value: Total value executed
        executions: Individual order executions
        events: Execution events log
        errors: Error messages
        metrics: Execution metrics
    """
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: ExecutionStatus = ExecutionStatus.PENDING
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    total_signals: int = 0
    orders_submitted: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    orders_cancelled: int = 0
    total_value: Decimal = Decimal("0")
    executions: List[OrderExecution] = field(default_factory=list)
    events: List[ExecutionEvent_] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# StrategyExecutor Class
# ============================================================================

class StrategyExecutor:
    """Orchestrates end-to-end strategy execution.

    Handles the complete trade lifecycle:
    1. Receive signals from signal provider
    2. Convert signals to orders
    3. Submit orders for execution
    4. Monitor order status
    5. Manage positions
    6. Handle errors and retries

    Attributes:
        config: Executor configuration
        signal_converter: Signal to order converter
        order_executor: Order execution handler
        position_manager: Position management
        event_handlers: Event callback handlers
    """

    def __init__(
        self,
        config: Optional[ExecutorConfig] = None,
        order_executor: Optional[OrderExecutor] = None,
        position_manager: Optional[PositionManager] = None,
        portfolio_value: Decimal = Decimal("100000"),
        current_prices: Optional[Dict[str, Decimal]] = None,
    ):
        """Initialize strategy executor.

        Args:
            config: Executor configuration
            order_executor: Order execution handler
            position_manager: Position management handler
            portfolio_value: Current portfolio value
            current_prices: Current market prices
        """
        self.config = config or ExecutorConfig()
        self.order_executor = order_executor
        self.position_manager = position_manager

        # Initialize signal converter
        self.signal_converter = SignalToOrderConverter(
            config=self.config.conversion_config,
            portfolio_value=portfolio_value,
            current_prices=current_prices or {},
        )

        # Event handlers
        self.event_handlers: Dict[ExecutionEvent, List[Callable]] = {
            event: [] for event in ExecutionEvent
        }

        # Execution state
        self._current_result: Optional[ExecutionResult] = None
        self._pending_orders: Dict[str, OrderExecution] = {}
        self._is_running = False

    def register_event_handler(
        self,
        event_type: ExecutionEvent,
        handler: Callable[[ExecutionEvent_], None],
    ) -> None:
        """Register a handler for execution events.

        Args:
            event_type: Type of event to handle
            handler: Callback function
        """
        self.event_handlers[event_type].append(handler)

    def _emit_event(
        self,
        event_type: ExecutionEvent,
        signal_id: Optional[str] = None,
        order_id: Optional[str] = None,
        symbol: str = "",
        message: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> ExecutionEvent_:
        """Emit an execution event.

        Args:
            event_type: Type of event
            signal_id: Associated signal ID
            order_id: Associated order ID
            symbol: Trading symbol
            message: Event message
            data: Additional data

        Returns:
            The emitted event
        """
        event = ExecutionEvent_(
            event_type=event_type,
            signal_id=signal_id,
            order_id=order_id,
            symbol=symbol,
            message=message,
            data=data or {},
        )

        # Log event
        if self.config.monitoring_config.log_all_events:
            logger.log(
                getattr(logging, self.config.monitoring_config.log_level),
                f"[{event_type.value}] {symbol}: {message}",
            )

        # Record event
        if self._current_result:
            self._current_result.events.append(event)

        # Call handlers
        for handler in self.event_handlers[event_type]:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

        return event

    def execute_signals(
        self,
        signals: List[TradingSignal],
    ) -> ExecutionResult:
        """Execute a list of trading signals synchronously.

        Args:
            signals: List of signals to execute

        Returns:
            ExecutionResult with all execution details
        """
        # Initialize result
        result = ExecutionResult(
            status=ExecutionStatus.PENDING,
            start_time=datetime.now(),
            total_signals=len(signals),
        )
        self._current_result = result

        self._emit_event(
            ExecutionEvent.STARTED,
            message=f"Starting execution of {len(signals)} signals",
        )

        try:
            result.status = ExecutionStatus.CONVERTING

            # Convert signals to orders
            for signal in signals:
                if signal.signal_type == SignalType.HOLD:
                    continue

                self._emit_event(
                    ExecutionEvent.SIGNAL_RECEIVED,
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    message=f"Received {signal.signal_type.value} signal",
                )

                execution = self._process_signal(signal)
                result.executions.append(execution)

                if execution.order_request:
                    result.orders_submitted += 1
                    self._emit_event(
                        ExecutionEvent.ORDER_CREATED,
                        signal_id=signal.signal_id,
                        order_id=execution.order_request.client_order_id,
                        symbol=signal.symbol,
                        message="Order created from signal",
                    )

            # In dry run mode, mark all as filled
            if self.config.dry_run:
                for execution in result.executions:
                    if execution.order_request:
                        execution.final_status = OrderStatus.FILLED
                        execution.fill_price = (
                            execution.order_request.limit_price or
                            self.signal_converter.current_prices.get(
                                execution.order_request.symbol,
                                Decimal("0")
                            )
                        )
                        execution.fill_quantity = execution.order_request.quantity
                        result.orders_filled += 1
                        result.total_value += (
                            execution.fill_price * execution.fill_quantity
                        )

            # Update final counts
            for execution in result.executions:
                if execution.final_status == OrderStatus.REJECTED:
                    result.orders_rejected += 1
                elif execution.final_status == OrderStatus.CANCELLED:
                    result.orders_cancelled += 1

            result.status = ExecutionStatus.COMPLETED
            result.end_time = datetime.now()

            self._emit_event(
                ExecutionEvent.COMPLETED,
                message=f"Execution complete: {result.orders_filled} filled, "
                        f"{result.orders_rejected} rejected",
            )

        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.end_time = datetime.now()
            result.errors.append(str(e))

            self._emit_event(
                ExecutionEvent.FAILED,
                message=f"Execution failed: {str(e)}",
            )

        # Calculate metrics
        result.metrics = self._calculate_metrics(result)
        self._current_result = None

        return result

    async def execute_signals_async(
        self,
        signals: List[TradingSignal],
    ) -> ExecutionResult:
        """Execute signals asynchronously with real order submission.

        Args:
            signals: List of signals to execute

        Returns:
            ExecutionResult with all execution details
        """
        if self.order_executor is None:
            raise ValueError("Order executor required for async execution")

        result = ExecutionResult(
            status=ExecutionStatus.PENDING,
            start_time=datetime.now(),
            total_signals=len(signals),
        )
        self._current_result = result
        self._is_running = True

        self._emit_event(
            ExecutionEvent.STARTED,
            message=f"Starting async execution of {len(signals)} signals",
        )

        try:
            result.status = ExecutionStatus.CONVERTING

            # Convert and submit orders concurrently
            tasks = []
            for signal in signals:
                if signal.signal_type == SignalType.HOLD:
                    continue

                self._emit_event(
                    ExecutionEvent.SIGNAL_RECEIVED,
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    message=f"Received {signal.signal_type.value} signal",
                )

                execution = self._process_signal(signal)
                result.executions.append(execution)

                if execution.order_request:
                    # Submit order asynchronously
                    task = self._submit_order_with_retry(execution)
                    tasks.append(task)

            result.status = ExecutionStatus.SUBMITTING

            # Wait for all orders to be submitted
            if tasks:
                submitted = await asyncio.gather(*tasks, return_exceptions=True)

                for i, sub_result in enumerate(submitted):
                    if isinstance(sub_result, Exception):
                        result.errors.append(str(sub_result))
                    else:
                        result.orders_submitted += 1

            result.status = ExecutionStatus.MONITORING

            # Monitor orders until filled or timeout
            await self._monitor_orders(result)

            # Update final counts
            for execution in result.executions:
                if execution.final_status == OrderStatus.FILLED:
                    result.orders_filled += 1
                    if execution.fill_price and execution.fill_quantity:
                        result.total_value += (
                            execution.fill_price * execution.fill_quantity
                        )
                elif execution.final_status == OrderStatus.REJECTED:
                    result.orders_rejected += 1
                elif execution.final_status == OrderStatus.CANCELLED:
                    result.orders_cancelled += 1

            result.status = ExecutionStatus.COMPLETED
            result.end_time = datetime.now()

            self._emit_event(
                ExecutionEvent.COMPLETED,
                message=f"Execution complete: {result.orders_filled} filled",
            )

        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.end_time = datetime.now()
            result.errors.append(str(e))

            self._emit_event(
                ExecutionEvent.FAILED,
                message=f"Execution failed: {str(e)}",
            )

        finally:
            self._is_running = False

        result.metrics = self._calculate_metrics(result)
        self._current_result = None

        return result

    def _process_signal(self, signal: TradingSignal) -> OrderExecution:
        """Process a single signal into an order execution.

        Args:
            signal: Trading signal to process

        Returns:
            OrderExecution record
        """
        execution = OrderExecution(signal=signal)

        # Convert signal to order
        conversion = self.signal_converter.convert(signal)
        execution.conversion_result = conversion

        if conversion.success and conversion.order_request:
            execution.order_request = conversion.order_request
        else:
            execution.error_message = conversion.error_message
            self._emit_event(
                ExecutionEvent.ERROR,
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                message=f"Signal conversion failed: {conversion.error_message}",
            )

        return execution

    async def _submit_order_with_retry(
        self,
        execution: OrderExecution,
    ) -> bool:
        """Submit order with retry logic.

        Args:
            execution: Order execution record

        Returns:
            True if submitted successfully
        """
        retry_config = self.config.retry_config
        delay_ms = retry_config.initial_delay_ms

        for attempt in range(retry_config.max_retries + 1):
            try:
                execution.submit_time = datetime.now()

                if self.order_executor:
                    order = await self.order_executor.submit_order(
                        execution.order_request
                    )
                    execution.submitted_order = order

                    self._emit_event(
                        ExecutionEvent.ORDER_SUBMITTED,
                        signal_id=execution.signal.signal_id if execution.signal else None,
                        order_id=order.broker_order_id,
                        symbol=execution.order_request.symbol,
                        message="Order submitted successfully",
                    )

                    # Track pending order
                    self._pending_orders[order.broker_order_id] = execution
                    return True

            except Exception as e:
                execution.retries = attempt + 1
                error_msg = f"Order submission failed (attempt {attempt + 1}): {e}"

                if attempt < retry_config.max_retries:
                    self._emit_event(
                        ExecutionEvent.RETRY,
                        signal_id=execution.signal.signal_id if execution.signal else None,
                        symbol=execution.order_request.symbol if execution.order_request else "",
                        message=error_msg,
                    )

                    # Apply delay
                    if retry_config.policy == RetryPolicy.EXPONENTIAL:
                        await asyncio.sleep(delay_ms / 1000)
                        delay_ms = min(
                            delay_ms * retry_config.backoff_multiplier,
                            retry_config.max_delay_ms,
                        )
                    elif retry_config.policy == RetryPolicy.FIXED:
                        await asyncio.sleep(retry_config.initial_delay_ms / 1000)
                else:
                    execution.error_message = str(e)
                    self._emit_event(
                        ExecutionEvent.ERROR,
                        signal_id=execution.signal.signal_id if execution.signal else None,
                        symbol=execution.order_request.symbol if execution.order_request else "",
                        message=f"Order submission failed after {attempt + 1} attempts: {e}",
                    )
                    return False

        return False

    async def _monitor_orders(self, result: ExecutionResult) -> None:
        """Monitor pending orders until completion.

        Args:
            result: Execution result to update
        """
        timeout = self.config.order_timeout_seconds
        start_time = time.time()

        while self._pending_orders and self._is_running:
            if time.time() - start_time > timeout:
                # Timeout - cancel remaining orders
                for order_id, execution in list(self._pending_orders.items()):
                    execution.final_status = OrderStatus.CANCELLED
                    execution.error_message = "Order timeout"

                    if self.order_executor:
                        try:
                            await self.order_executor.cancel_order(order_id)
                        except Exception:
                            pass

                    self._emit_event(
                        ExecutionEvent.ORDER_CANCELLED,
                        order_id=order_id,
                        message="Order cancelled due to timeout",
                    )

                self._pending_orders.clear()
                break

            # Check each pending order
            for order_id, execution in list(self._pending_orders.items()):
                if self.order_executor:
                    try:
                        order = await self.order_executor.get_order_status(order_id)
                        execution.submitted_order = order

                        if order.status == OrderStatus.FILLED:
                            execution.final_status = OrderStatus.FILLED
                            execution.fill_price = order.filled_avg_price
                            execution.fill_quantity = order.filled_quantity
                            execution.fill_time = datetime.now()

                            if execution.submit_time:
                                execution.latency_ms = int(
                                    (execution.fill_time - execution.submit_time).total_seconds() * 1000
                                )

                            self._emit_event(
                                ExecutionEvent.ORDER_FILLED,
                                order_id=order_id,
                                symbol=order.symbol,
                                message=f"Order filled at {order.filled_avg_price}",
                            )

                            del self._pending_orders[order_id]

                            # Update position
                            if self.position_manager:
                                self.position_manager.update_position(
                                    order.symbol,
                                    order.filled_quantity,
                                    order.filled_avg_price,
                                )

                        elif order.status == OrderStatus.REJECTED:
                            execution.final_status = OrderStatus.REJECTED

                            self._emit_event(
                                ExecutionEvent.ORDER_REJECTED,
                                order_id=order_id,
                                symbol=order.symbol,
                                message="Order rejected",
                            )

                            del self._pending_orders[order_id]

                        elif order.status == OrderStatus.CANCELLED:
                            execution.final_status = OrderStatus.CANCELLED

                            self._emit_event(
                                ExecutionEvent.ORDER_CANCELLED,
                                order_id=order_id,
                                symbol=order.symbol,
                                message="Order cancelled",
                            )

                            del self._pending_orders[order_id]

                    except Exception as e:
                        logger.error(f"Error checking order {order_id}: {e}")

            # Small delay between checks
            await asyncio.sleep(0.1)

    def _calculate_metrics(self, result: ExecutionResult) -> Dict[str, Any]:
        """Calculate execution metrics.

        Args:
            result: Execution result

        Returns:
            Dict of metrics
        """
        metrics = {
            "total_signals": result.total_signals,
            "orders_submitted": result.orders_submitted,
            "orders_filled": result.orders_filled,
            "fill_rate": (
                result.orders_filled / result.orders_submitted
                if result.orders_submitted > 0 else 0
            ),
            "orders_rejected": result.orders_rejected,
            "orders_cancelled": result.orders_cancelled,
            "total_value": str(result.total_value),
            "total_errors": len(result.errors),
        }

        # Calculate latency metrics
        latencies = [
            e.latency_ms for e in result.executions
            if e.latency_ms is not None
        ]
        if latencies:
            metrics["avg_latency_ms"] = sum(latencies) / len(latencies)
            metrics["min_latency_ms"] = min(latencies)
            metrics["max_latency_ms"] = max(latencies)

        # Calculate retry metrics
        total_retries = sum(e.retries for e in result.executions)
        metrics["total_retries"] = total_retries

        # Calculate duration
        if result.end_time:
            duration = (result.end_time - result.start_time).total_seconds()
            metrics["duration_seconds"] = duration

        return metrics

    def cancel_execution(self) -> None:
        """Cancel ongoing execution."""
        self._is_running = False

        if self._current_result:
            self._current_result.status = ExecutionStatus.CANCELLED

            self._emit_event(
                ExecutionEvent.FAILED,
                message="Execution cancelled by user",
            )

    def update_prices(self, prices: Dict[str, Decimal]) -> None:
        """Update current market prices.

        Args:
            prices: Dict of symbol to price
        """
        for symbol, price in prices.items():
            self.signal_converter.update_price(symbol, price)

    def update_portfolio_value(self, value: Decimal) -> None:
        """Update portfolio value.

        Args:
            value: New portfolio value
        """
        self.signal_converter.update_portfolio_value(value)

    def get_execution_summary(self, result: ExecutionResult) -> str:
        """Generate a summary report of execution.

        Args:
            result: Execution result

        Returns:
            Formatted summary string
        """
        lines = [
            "# Execution Summary",
            f"**Status**: {result.status.value}",
            f"**Start**: {result.start_time}",
            f"**End**: {result.end_time}",
            "",
            "## Order Statistics",
            f"- Signals processed: {result.total_signals}",
            f"- Orders submitted: {result.orders_submitted}",
            f"- Orders filled: {result.orders_filled}",
            f"- Orders rejected: {result.orders_rejected}",
            f"- Orders cancelled: {result.orders_cancelled}",
            f"- Total value: ${result.total_value:,.2f}",
            "",
        ]

        if result.metrics:
            lines.extend([
                "## Metrics",
                f"- Fill rate: {result.metrics.get('fill_rate', 0):.1%}",
                f"- Avg latency: {result.metrics.get('avg_latency_ms', 0):.0f}ms",
                f"- Total retries: {result.metrics.get('total_retries', 0)}",
                f"- Duration: {result.metrics.get('duration_seconds', 0):.1f}s",
                "",
            ])

        if result.errors:
            lines.extend([
                "## Errors",
            ])
            for error in result.errors[:5]:
                lines.append(f"- {error}")

        return "\n".join(lines)
