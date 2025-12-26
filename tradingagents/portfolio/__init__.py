"""Portfolio module for portfolio state management.

This module provides portfolio state tracking including:
- Current holdings with cost basis and market values
- Multi-currency cash balances
- Real-time mark-to-market valuation
- Portfolio snapshots for historical analysis

Issue #29: [PORT-28] Portfolio state - holdings, cash, mark-to-market

Submodules:
    portfolio_state: Core portfolio state management

Classes:
    Enums:
    - Currency: Supported currencies (USD, EUR, GBP, etc.)
    - HoldingType: Type of holding (LONG, SHORT)

    Data Classes:
    - Holding: Individual holding/position in the portfolio
    - CashBalance: Cash balance in a specific currency
    - PortfolioSnapshot: Immutable snapshot of portfolio state

    Main Class:
    - PortfolioState: Live portfolio state with mark-to-market updates

    Protocols:
    - PriceProvider: Protocol for price data providers
    - ExchangeRateProvider: Protocol for currency exchange rate providers

Example:
    >>> from tradingagents.portfolio import (
    ...     PortfolioState,
    ...     Holding,
    ...     Currency,
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

__all__ = [
    # Enums
    "Currency",
    "HoldingType",
    # Data Classes
    "Holding",
    "CashBalance",
    "PortfolioSnapshot",
    # Main Class
    "PortfolioState",
    # Protocols
    "PriceProvider",
    "ExchangeRateProvider",
]
