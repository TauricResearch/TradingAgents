"""Strategy module for trading strategy execution.

This module provides strategy orchestration including:
- Signal to order conversion
- End-to-end strategy execution
- Position management

Issue #36: [STRAT-35] Signal to order converter
Issue #37: [STRAT-36] Strategy executor - end-to-end orchestration

Submodules:
    signal_to_order: Convert signals to executable orders

Classes:
    Enums:
    - SignalType: Type of trading signal (buy, sell, hold)
    - SignalStrength: Strength of signal (strong, moderate, weak)
    - PositionSizingMethod: Position sizing method
    - StopLossType: Type of stop loss
    - TakeProfitType: Type of take profit
    - OrderValidationError: Order validation error types

    Data Classes:
    - TradingSignal: A trading signal from strategy
    - PositionSizingConfig: Position sizing configuration
    - StopLossConfig: Stop loss configuration
    - TakeProfitConfig: Take profit configuration
    - ConversionConfig: Signal to order conversion config
    - OrderValidationResult: Result of order validation
    - ConversionResult: Result of signal to order conversion

    Main Classes:
    - SignalToOrderConverter: Converts signals to orders

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

__all__ = [
    # Enums
    "SignalType",
    "SignalStrength",
    "PositionSizingMethod",
    "StopLossType",
    "TakeProfitType",
    "OrderValidationError",
    # Data Classes
    "TradingSignal",
    "PositionSizingConfig",
    "StopLossConfig",
    "TakeProfitConfig",
    "ConversionConfig",
    "OrderValidationResult",
    "ConversionResult",
    # Main Class
    "SignalToOrderConverter",
]
