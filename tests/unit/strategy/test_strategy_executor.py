"""Tests for Strategy Executor.

Issue #37: [STRAT-36] Strategy executor - end-to-end orchestration
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from tradingagents.strategy.strategy_executor import (
    # Enums
    ExecutionStatus,
    RetryPolicy,
    ExecutionEvent,
    # Data Classes
    RetryConfig,
    MonitoringConfig,
    ExecutorConfig,
    OrderExecution,
    ExecutionResult,
    ExecutionEvent_ as EventRecord,
    # Main Class
    StrategyExecutor,
)
from tradingagents.strategy.signal_to_order import (
    TradingSignal,
    SignalType,
    SignalStrength,
    ConversionConfig,
)
from tradingagents.execution.broker_base import (
    Order,
    OrderStatus,
    OrderSide,
    OrderType,
)


# ============================================================================
# Enum Tests
# ============================================================================

class TestExecutionStatus:
    """Tests for ExecutionStatus enum."""

    def test_all_statuses_defined(self):
        """Verify all statuses exist."""
        assert ExecutionStatus.PENDING
        assert ExecutionStatus.CONVERTING
        assert ExecutionStatus.SUBMITTING
        assert ExecutionStatus.EXECUTING
        assert ExecutionStatus.MONITORING
        assert ExecutionStatus.COMPLETED
        assert ExecutionStatus.FAILED
        assert ExecutionStatus.CANCELLED

    def test_status_values(self):
        """Verify status values."""
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.COMPLETED.value == "completed"


class TestRetryPolicy:
    """Tests for RetryPolicy enum."""

    def test_all_policies_defined(self):
        """Verify all policies exist."""
        assert RetryPolicy.NONE
        assert RetryPolicy.IMMEDIATE
        assert RetryPolicy.EXPONENTIAL
        assert RetryPolicy.FIXED


class TestExecutionEvent:
    """Tests for ExecutionEvent enum."""

    def test_all_events_defined(self):
        """Verify all events exist."""
        assert ExecutionEvent.STARTED
        assert ExecutionEvent.SIGNAL_RECEIVED
        assert ExecutionEvent.ORDER_CREATED
        assert ExecutionEvent.ORDER_SUBMITTED
        assert ExecutionEvent.ORDER_FILLED
        assert ExecutionEvent.ORDER_REJECTED
        assert ExecutionEvent.ORDER_CANCELLED
        assert ExecutionEvent.ERROR
        assert ExecutionEvent.RETRY
        assert ExecutionEvent.COMPLETED
        assert ExecutionEvent.FAILED


# ============================================================================
# Data Class Tests
# ============================================================================

class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = RetryConfig()
        assert config.policy == RetryPolicy.EXPONENTIAL
        assert config.max_retries == 3
        assert config.initial_delay_ms == 100

    def test_custom_config(self):
        """Test creating custom config."""
        config = RetryConfig(
            policy=RetryPolicy.FIXED,
            max_retries=5,
        )
        assert config.policy == RetryPolicy.FIXED
        assert config.max_retries == 5


class TestMonitoringConfig:
    """Tests for MonitoringConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = MonitoringConfig()
        assert config.log_all_events is True
        assert config.track_latency is True
        assert config.alert_on_failure is True


class TestExecutorConfig:
    """Tests for ExecutorConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = ExecutorConfig()
        assert config.max_concurrent_orders == 10
        assert config.order_timeout_seconds == 300
        assert config.dry_run is False


class TestOrderExecution:
    """Tests for OrderExecution dataclass."""

    def test_default_creation(self):
        """Test creating execution with defaults."""
        execution = OrderExecution()
        assert execution.execution_id is not None
        assert execution.final_status == OrderStatus.PENDING_NEW
        assert execution.retries == 0


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_default_creation(self):
        """Test creating result with defaults."""
        result = ExecutionResult()
        assert result.result_id is not None
        assert result.status == ExecutionStatus.PENDING
        assert result.total_signals == 0
        assert result.orders_filled == 0


class TestEventRecord:
    """Tests for ExecutionEvent_ dataclass."""

    def test_default_creation(self):
        """Test creating event with defaults."""
        event = EventRecord()
        assert event.event_id is not None
        assert event.event_type == ExecutionEvent.STARTED
        assert event.timestamp is not None


# ============================================================================
# StrategyExecutor Tests
# ============================================================================

class TestStrategyExecutor:
    """Tests for StrategyExecutor class."""

    @pytest.fixture
    def executor(self):
        """Create default executor."""
        return StrategyExecutor(
            portfolio_value=Decimal("100000"),
            current_prices={"AAPL": Decimal("150.00")},
        )

    @pytest.fixture
    def buy_signal(self):
        """Create a buy signal."""
        return TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            confidence=Decimal("0.8"),
        )

    @pytest.fixture
    def sell_signal(self):
        """Create a sell signal."""
        return TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.SELL,
            strength=SignalStrength.MODERATE,
        )

    @pytest.fixture
    def hold_signal(self):
        """Create a hold signal."""
        return TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.HOLD,
        )

    def test_initialization(self, executor):
        """Test executor initialization."""
        assert executor.signal_converter is not None
        assert executor.config is not None
        assert executor.order_executor is None

    def test_custom_config(self):
        """Test executor with custom config."""
        config = ExecutorConfig(dry_run=True)
        executor = StrategyExecutor(config=config)
        assert executor.config.dry_run is True

    def test_execute_buy_signal(self, executor, buy_signal):
        """Test executing a buy signal."""
        result = executor.execute_signals([buy_signal])
        assert result.status == ExecutionStatus.COMPLETED
        assert result.total_signals == 1
        assert len(result.executions) == 1

    def test_execute_multiple_signals(self, executor, buy_signal, sell_signal):
        """Test executing multiple signals."""
        result = executor.execute_signals([buy_signal, sell_signal])
        assert result.status == ExecutionStatus.COMPLETED
        assert result.total_signals == 2
        assert len(result.executions) == 2

    def test_hold_signal_skipped(self, executor, hold_signal):
        """Test that HOLD signals are skipped."""
        result = executor.execute_signals([hold_signal])
        assert result.status == ExecutionStatus.COMPLETED
        assert result.total_signals == 1
        assert len(result.executions) == 0

    def test_dry_run_mode(self, buy_signal):
        """Test dry run mode marks orders as filled."""
        config = ExecutorConfig(dry_run=True)
        executor = StrategyExecutor(
            config=config,
            current_prices={"AAPL": Decimal("150.00")},
        )
        result = executor.execute_signals([buy_signal])
        assert result.orders_filled == 1
        assert result.total_value > 0

    def test_event_emission(self, executor, buy_signal):
        """Test that events are emitted."""
        events_received = []

        def handler(event):
            events_received.append(event)

        executor.register_event_handler(ExecutionEvent.STARTED, handler)
        executor.register_event_handler(ExecutionEvent.SIGNAL_RECEIVED, handler)

        executor.execute_signals([buy_signal])

        assert len(events_received) >= 2
        assert events_received[0].event_type == ExecutionEvent.STARTED

    def test_event_handler_registration(self, executor):
        """Test registering event handlers."""
        handler = MagicMock()
        executor.register_event_handler(ExecutionEvent.COMPLETED, handler)
        assert handler in executor.event_handlers[ExecutionEvent.COMPLETED]

    def test_events_logged(self, executor, buy_signal):
        """Test that events are logged to result."""
        result = executor.execute_signals([buy_signal])
        assert len(result.events) > 0
        event_types = [e.event_type for e in result.events]
        assert ExecutionEvent.STARTED in event_types
        assert ExecutionEvent.COMPLETED in event_types

    def test_metrics_calculated(self, executor, buy_signal):
        """Test that metrics are calculated."""
        result = executor.execute_signals([buy_signal])
        assert "total_signals" in result.metrics
        assert "orders_submitted" in result.metrics
        assert "fill_rate" in result.metrics

    def test_execution_summary(self, executor, buy_signal):
        """Test generating execution summary."""
        result = executor.execute_signals([buy_signal])
        summary = executor.get_execution_summary(result)
        assert "Execution Summary" in summary
        assert "Status" in summary
        assert "Order Statistics" in summary

    def test_update_prices(self, executor):
        """Test updating prices."""
        executor.update_prices({"MSFT": Decimal("300.00")})
        assert executor.signal_converter.current_prices["MSFT"] == Decimal("300.00")

    def test_update_portfolio_value(self, executor):
        """Test updating portfolio value."""
        executor.update_portfolio_value(Decimal("200000"))
        assert executor.signal_converter.portfolio_value == Decimal("200000")

    def test_cancel_execution(self, executor):
        """Test cancelling execution."""
        executor._current_result = ExecutionResult()
        executor._is_running = True
        executor.cancel_execution()
        assert executor._is_running is False
        assert executor._current_result.status == ExecutionStatus.CANCELLED

    def test_failed_conversion(self, executor):
        """Test handling failed signal conversion."""
        signal = TradingSignal(
            symbol="UNKNOWN",  # No price available
            signal_type=SignalType.BUY,
        )
        result = executor.execute_signals([signal])
        assert result.status == ExecutionStatus.COMPLETED
        assert len(result.executions) == 1
        assert result.executions[0].error_message != ""

    def test_execution_result_timing(self, executor, buy_signal):
        """Test that timing is tracked."""
        result = executor.execute_signals([buy_signal])
        assert result.start_time is not None
        assert result.end_time is not None
        assert result.end_time >= result.start_time

    def test_empty_signals_list(self, executor):
        """Test executing empty signal list."""
        result = executor.execute_signals([])
        assert result.status == ExecutionStatus.COMPLETED
        assert result.total_signals == 0
        assert len(result.executions) == 0


class TestStrategyExecutorAsync:
    """Tests for async execution."""

    @pytest.fixture
    def mock_order_executor(self):
        """Create mock order executor."""
        mock = AsyncMock()
        mock.submit_order = AsyncMock(return_value=Order(
            broker_order_id="test-order-1",
            client_order_id="client-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
            status=OrderStatus.PENDING_NEW,
            submitted_at=datetime.now(),
        ))
        mock.get_order_status = AsyncMock(return_value=Order(
            broker_order_id="test-order-1",
            client_order_id="client-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
            filled_quantity=Decimal("10"),
            filled_avg_price=Decimal("150.00"),
            status=OrderStatus.FILLED,
            submitted_at=datetime.now(),
            filled_at=datetime.now(),
        ))
        return mock

    @pytest.fixture
    def executor_with_mock(self, mock_order_executor):
        """Create executor with mock order executor."""
        return StrategyExecutor(
            order_executor=mock_order_executor,
            portfolio_value=Decimal("100000"),
            current_prices={"AAPL": Decimal("150.00")},
        )

    @pytest.fixture
    def buy_signal(self):
        """Create a buy signal."""
        return TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
        )

    @pytest.mark.asyncio
    async def test_async_execution(self, executor_with_mock, buy_signal):
        """Test async signal execution."""
        result = await executor_with_mock.execute_signals_async([buy_signal])
        assert result.status == ExecutionStatus.COMPLETED
        assert result.orders_submitted >= 1

    @pytest.mark.asyncio
    async def test_async_requires_executor(self, buy_signal):
        """Test that async requires order executor."""
        executor = StrategyExecutor(
            current_prices={"AAPL": Decimal("150.00")},
        )
        with pytest.raises(ValueError, match="Order executor required"):
            await executor.execute_signals_async([buy_signal])

    @pytest.mark.asyncio
    async def test_order_submission(self, executor_with_mock, buy_signal, mock_order_executor):
        """Test that orders are submitted."""
        await executor_with_mock.execute_signals_async([buy_signal])
        mock_order_executor.submit_order.assert_called()

    @pytest.mark.asyncio
    async def test_order_monitoring(self, executor_with_mock, buy_signal, mock_order_executor):
        """Test that orders are monitored."""
        await executor_with_mock.execute_signals_async([buy_signal])
        mock_order_executor.get_order_status.assert_called()


class TestRetryBehavior:
    """Tests for retry behavior."""

    @pytest.fixture
    def failing_executor(self):
        """Create executor with failing order executor."""
        mock = AsyncMock()
        mock.submit_order = AsyncMock(side_effect=Exception("Network error"))
        return StrategyExecutor(
            order_executor=mock,
            config=ExecutorConfig(
                retry_config=RetryConfig(
                    policy=RetryPolicy.IMMEDIATE,
                    max_retries=2,
                ),
            ),
            current_prices={"AAPL": Decimal("150.00")},
        )

    @pytest.fixture
    def buy_signal(self):
        """Create a buy signal."""
        return TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
        )

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, failing_executor, buy_signal):
        """Test that retries occur on failure."""
        result = await failing_executor.execute_signals_async([buy_signal])
        assert result.status == ExecutionStatus.COMPLETED
        # Check that retry events were emitted
        retry_events = [e for e in result.events if e.event_type == ExecutionEvent.RETRY]
        assert len(retry_events) > 0
        # Check that executions have error messages
        assert len(result.executions) > 0
        assert result.executions[0].error_message != ""


# ============================================================================
# Integration Tests
# ============================================================================

class TestStrategyExecutorIntegration:
    """Integration tests for strategy executor."""

    def test_full_workflow(self):
        """Test complete execution workflow."""
        # Setup executor with dry run
        config = ExecutorConfig(
            dry_run=True,
            enable_stop_orders=True,
            enable_take_profit=True,
        )

        executor = StrategyExecutor(
            config=config,
            portfolio_value=Decimal("100000"),
            current_prices={
                "AAPL": Decimal("150.00"),
                "MSFT": Decimal("300.00"),
            },
        )

        # Generate signals
        signals = [
            TradingSignal(
                symbol="AAPL",
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG,
            ),
            TradingSignal(
                symbol="MSFT",
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
            ),
        ]

        # Execute
        result = executor.execute_signals(signals)

        # Verify
        assert result.status == ExecutionStatus.COMPLETED
        assert result.orders_filled == 2
        assert result.total_value > 0

    def test_module_imports(self):
        """Test that all classes are exported from module."""
        from tradingagents.strategy import (
            ExecutionStatus,
            RetryPolicy,
            ExecutionEvent,
            RetryConfig,
            MonitoringConfig,
            ExecutorConfig,
            OrderExecution,
            ExecutionResult,
            StrategyExecutor,
        )

        # All imports successful
        assert ExecutionStatus.COMPLETED is not None
        assert StrategyExecutor is not None

    def test_event_driven_execution(self):
        """Test event-driven execution flow."""
        executor = StrategyExecutor(
            config=ExecutorConfig(dry_run=True),
            current_prices={"AAPL": Decimal("150.00")},
        )

        events_log = []

        # Register handlers for all events
        for event_type in ExecutionEvent:
            executor.register_event_handler(
                event_type,
                lambda e, et=event_type: events_log.append(et),
            )

        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
        )

        executor.execute_signals([signal])

        # Should have key events
        assert ExecutionEvent.STARTED in events_log
        assert ExecutionEvent.SIGNAL_RECEIVED in events_log
        assert ExecutionEvent.ORDER_CREATED in events_log
        assert ExecutionEvent.COMPLETED in events_log

    def test_error_handling(self):
        """Test error handling in execution."""
        executor = StrategyExecutor(
            current_prices={},  # No prices - will fail
        )

        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
        )

        result = executor.execute_signals([signal])

        # Should complete (not crash) but have errors
        assert result.status == ExecutionStatus.COMPLETED
        assert len(result.executions) == 1
        assert result.executions[0].error_message != ""
