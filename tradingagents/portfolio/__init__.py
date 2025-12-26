"""Portfolio module for portfolio state and performance management.

This module provides portfolio state tracking and performance metrics:
- Current holdings with cost basis and market values
- Multi-currency cash balances
- Real-time mark-to-market valuation
- Portfolio snapshots for historical analysis
- Performance metrics (Sharpe, Sortino, Calmar ratios)
- Drawdown analysis
- Trade statistics
- Benchmark comparison

Issue #29: [PORT-28] Portfolio state - holdings, cash, mark-to-market
Issue #31: [PORT-30] Performance metrics - Sharpe, drawdown, returns

Submodules:
    portfolio_state: Core portfolio state management
    performance: Performance metrics calculation

Classes:
    Enums:
    - Currency: Supported currencies (USD, EUR, GBP, etc.)
    - HoldingType: Type of holding (LONG, SHORT)
    - Period: Time period for performance calculations

    Data Classes:
    - Holding: Individual holding/position in the portfolio
    - CashBalance: Cash balance in a specific currency
    - PortfolioSnapshot: Immutable snapshot of portfolio state
    - ReturnSeries: Series of returns over time
    - DrawdownInfo: Information about a drawdown period
    - TradeStats: Trade-level statistics
    - PerformanceMetrics: Complete performance metrics summary

    Main Classes:
    - PortfolioState: Live portfolio state with mark-to-market updates
    - PerformanceCalculator: Calculator for performance metrics

    Protocols:
    - PriceProvider: Protocol for price data providers
    - ExchangeRateProvider: Protocol for currency exchange rate providers

Example:
    >>> from tradingagents.portfolio import (
    ...     PortfolioState,
    ...     Holding,
    ...     Currency,
    ...     PerformanceCalculator,
    ...     ReturnSeries,
    ... )
    >>> from decimal import Decimal
    >>>
    >>> # Create portfolio with USD as base currency
    >>> portfolio = PortfolioState(base_currency=Currency.USD)
    >>>
    >>> # Add cash
    >>> portfolio.add_cash(Currency.USD, Decimal("10000"))
    >>>
    >>> # Add a holding
    >>> portfolio.add_holding(Holding(
    ...     symbol="AAPL",
    ...     quantity=Decimal("100"),
    ...     avg_cost=Decimal("150"),
    ...     current_price=Decimal("160"),
    ... ))
    >>>
    >>> # Check portfolio value
    >>> print(f"Total value: ${portfolio.total_value}")
    Total value: $26000.00
"""

from .portfolio_state import (
    # Enums
    Currency,
    HoldingType,
    # Data Classes
    Holding,
    CashBalance,
    PortfolioSnapshot,
    # Main Class
    PortfolioState,
    # Protocols
    PriceProvider,
    ExchangeRateProvider,
)

from .performance import (
    # Enums
    Period,
    # Data Classes
    ReturnSeries,
    DrawdownInfo,
    TradeStats,
    PerformanceMetrics,
    # Main Class
    PerformanceCalculator,
    # Utility Functions
    calculate_cagr,
    calculate_rolling_returns,
    calculate_monthly_returns,
    calculate_yearly_returns,
)

__all__ = [
    # Portfolio State Enums
    "Currency",
    "HoldingType",
    # Portfolio State Data Classes
    "Holding",
    "CashBalance",
    "PortfolioSnapshot",
    # Portfolio State Main Class
    "PortfolioState",
    # Portfolio State Protocols
    "PriceProvider",
    "ExchangeRateProvider",
    # Performance Enums
    "Period",
    # Performance Data Classes
    "ReturnSeries",
    "DrawdownInfo",
    "TradeStats",
    "PerformanceMetrics",
    # Performance Main Class
    "PerformanceCalculator",
    # Performance Utility Functions
    "calculate_cagr",
    "calculate_rolling_returns",
    "calculate_monthly_returns",
    "calculate_yearly_returns",
]
