"""Strategy module for trading strategy execution.

This module provides strategy orchestration including:
- Signal to order conversion
- End-to-end strategy execution
- Position management

Issue #36: [STRAT-35] Signal to order converter
Issue #37: [STRAT-36] Strategy executor - end-to-end orchestration

Submodules:
    signal_to_order: Convert signals to executable orders
    strategy_executor: End-to-end strategy orchestration

Classes:
    Enums:
    - SignalType: Type of trading signal (buy, sell, hold)
    - SignalStrength: Strength of signal (strong, moderate, weak)
    - PositionSizingMethod: Position sizing method
    - StopLossType: Type of stop loss
    - TakeProfitType: Type of take profit
    - OrderValidationError: Order validation error types
    - ExecutionStatus: Status of strategy execution
    - RetryPolicy: Retry policy for failed operations
    - ExecutionEvent: Events during execution

    Data Classes:
    - TradingSignal: A trading signal from strategy
    - PositionSizingConfig: Position sizing configuration
    - StopLossConfig: Stop loss configuration
    - TakeProfitConfig: Take profit configuration
    - ConversionConfig: Signal to order conversion config
    - OrderValidationResult: Result of order validation
    - ConversionResult: Result of signal to order conversion
    - RetryConfig: Retry behavior configuration
    - MonitoringConfig: Execution monitoring config
    - ExecutorConfig: Strategy executor configuration
    - OrderExecution: Record of order execution
    - ExecutionResult: Complete execution result

    Main Classes:
    - SignalToOrderConverter: Converts signals to orders
    - StrategyExecutor: End-to-end strategy orchestration

Example:
    >>> from tradingagents.strategy import (
    ...     SignalToOrderConverter,
    ...     TradingSignal,
    ...     SignalType,
    ...     ConversionConfig,
    ... )
    >>> from decimal import Decimal
    >>>
    >>> converter = SignalToOrderConverter(
    ...     portfolio_value=Decimal("100000"),
    ...     current_prices={"AAPL": Decimal("150.00")},
    ... )
    >>>
    >>> signal = TradingSignal(
    ...     symbol="AAPL",
    ...     signal_type=SignalType.BUY,
    ... )
    >>> result = converter.convert(signal)
    >>> if result.success:
    ...     print(f"Order: {result.order_request}")
"""

from .signal_to_order import (
    # Enums
    SignalType,
    SignalStrength,
    PositionSizingMethod,
    StopLossType,
    TakeProfitType,
    OrderValidationError,
    # Data Classes
    TradingSignal,
    PositionSizingConfig,
    StopLossConfig,
    TakeProfitConfig,
    ConversionConfig,
    OrderValidationResult,
    ConversionResult,
    # Main Class
    SignalToOrderConverter,
)

from .strategy_executor import (
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
    # Main Class
    StrategyExecutor,
)

__all__ = [
    # Signal to Order Enums
    "SignalType",
    "SignalStrength",
    "PositionSizingMethod",
    "StopLossType",
    "TakeProfitType",
    "OrderValidationError",
    # Signal to Order Data Classes
    "TradingSignal",
    "PositionSizingConfig",
    "StopLossConfig",
    "TakeProfitConfig",
    "ConversionConfig",
    "OrderValidationResult",
    "ConversionResult",
    # Signal to Order Main Class
    "SignalToOrderConverter",
    # Strategy Executor Enums
    "ExecutionStatus",
    "RetryPolicy",
    "ExecutionEvent",
    # Strategy Executor Data Classes
    "RetryConfig",
    "MonitoringConfig",
    "ExecutorConfig",
    "OrderExecution",
    "ExecutionResult",
    # Strategy Executor Main Class
    "StrategyExecutor",
]
