"""Backtest module for historical strategy replay.

Issue #42: [BT-41] Backtest engine - historical replay, slippage

This module provides backtesting capabilities:
- Historical price data replay
- Realistic slippage modeling
- Commission/fee handling
- Position and portfolio tracking
- Trade execution simulation
- Performance metrics calculation

Classes:
    Enums:
    - OrderSide: Buy or sell
    - OrderType: Market, limit, stop, stop_limit
    - FillStatus: Order fill status

    Data Classes:
    - OHLCV: Price bar data
    - Signal: Trading signal
    - BacktestConfig: Backtest configuration
    - BacktestPosition: Position tracking
    - BacktestTrade: Trade record
    - BacktestSnapshot: Portfolio snapshot
    - BacktestResult: Complete result with metrics

    Slippage Models:
    - SlippageModel: Base class
    - NoSlippage: No slippage
    - FixedSlippage: Fixed amount per share
    - PercentageSlippage: Percentage of price
    - VolumeSlippage: Volume-impact model

    Commission Models:
    - CommissionModel: Base class
    - NoCommission: No commission
    - FixedCommission: Fixed per trade
    - PerShareCommission: Per share commission
    - PercentageCommission: Percentage of value
    - TieredCommission: Tiered by trade value

    Main Classes:
    - BacktestEngine: Main backtest engine

Example:
    >>> from tradingagents.backtest import (
    ...     BacktestEngine,
    ...     BacktestConfig,
    ...     OHLCV,
    ...     Signal,
    ...     OrderSide,
    ...     PercentageSlippage,
    ...     PercentageCommission,
    ... )
    >>> from decimal import Decimal
    >>> from datetime import datetime
    >>>
    >>> config = BacktestConfig(
    ...     initial_capital=Decimal("100000"),
    ...     slippage_model=PercentageSlippage(Decimal("0.1")),
    ...     commission_model=PercentageCommission(Decimal("0.1")),
    ... )
    >>> engine = BacktestEngine(config)
    >>>
    >>> price_data = {
    ...     "AAPL": [
    ...         OHLCV(datetime(2023, 1, 3), 130, 132, 129, 131, 1000000),
    ...         OHLCV(datetime(2023, 1, 4), 131, 135, 130, 134, 1200000),
    ...     ],
    ... }
    >>> signals = [
    ...     Signal(datetime(2023, 1, 3), "AAPL", OrderSide.BUY, Decimal("100")),
    ... ]
    >>> result = engine.run(price_data, signals)
    >>> print(f"Return: {result.total_return}%")
"""

from .backtest_engine import (
    # Enums
    OrderSide,
    OrderType,
    FillStatus,
    # Data Classes
    OHLCV,
    Signal,
    BacktestConfig,
    BacktestPosition,
    BacktestTrade,
    BacktestSnapshot,
    BacktestResult,
    # Slippage Models
    SlippageModel,
    NoSlippage,
    FixedSlippage,
    PercentageSlippage,
    VolumeSlippage,
    # Commission Models
    CommissionModel,
    NoCommission,
    FixedCommission,
    PerShareCommission,
    PercentageCommission,
    TieredCommission,
    # Main Classes
    BacktestEngine,
    # Factory Functions
    create_backtest_engine,
)

from .results_analyzer import (
    # Enums
    TimeFrame,
    TradeDirection,
    # Data Classes
    TradeAnalysis,
    TradePattern,
    PerformanceBreakdown,
    RiskMetrics,
    TradeStatistics,
    BenchmarkComparison,
    DrawdownAnalysis,
    AnalysisResult,
    # Main Classes
    ResultsAnalyzer,
    # Factory Functions
    create_results_analyzer,
)

__all__ = [
    # Enums
    "OrderSide",
    "OrderType",
    "FillStatus",
    # Data Classes
    "OHLCV",
    "Signal",
    "BacktestConfig",
    "BacktestPosition",
    "BacktestTrade",
    "BacktestSnapshot",
    "BacktestResult",
    # Slippage Models
    "SlippageModel",
    "NoSlippage",
    "FixedSlippage",
    "PercentageSlippage",
    "VolumeSlippage",
    # Commission Models
    "CommissionModel",
    "NoCommission",
    "FixedCommission",
    "PerShareCommission",
    "PercentageCommission",
    "TieredCommission",
    # Main Classes
    "BacktestEngine",
    "ResultsAnalyzer",
    # Factory Functions
    "create_backtest_engine",
    "create_results_analyzer",
    # Results Analyzer Enums
    "TimeFrame",
    "TradeDirection",
    # Results Analyzer Data Classes
    "TradeAnalysis",
    "TradePattern",
    "PerformanceBreakdown",
    "RiskMetrics",
    "TradeStatistics",
    "BenchmarkComparison",
    "DrawdownAnalysis",
    "AnalysisResult",
]
