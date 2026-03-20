"""Portfolio Manager — public package exports.

Import the primary interface classes from this package:

    from tradingagents.portfolio import (
        PortfolioRepository,
        Portfolio,
        Holding,
        Trade,
        PortfolioSnapshot,
        PortfolioError,
        PortfolioNotFoundError,
        InsufficientCashError,
        InsufficientSharesError,
    )
"""

from __future__ import annotations

from tradingagents.portfolio.exceptions import (
    PortfolioError,
    PortfolioNotFoundError,
    HoldingNotFoundError,
    DuplicatePortfolioError,
    InsufficientCashError,
    InsufficientSharesError,
    ConstraintViolationError,
    ReportStoreError,
)
from tradingagents.portfolio.models import (
    Holding,
    Portfolio,
    PortfolioSnapshot,
    Trade,
)
from tradingagents.portfolio.repository import PortfolioRepository

__all__ = [
    # Models
    "Portfolio",
    "Holding",
    "Trade",
    "PortfolioSnapshot",
    # Repository (primary interface)
    "PortfolioRepository",
    # Exceptions
    "PortfolioError",
    "PortfolioNotFoundError",
    "HoldingNotFoundError",
    "DuplicatePortfolioError",
    "InsufficientCashError",
    "InsufficientSharesError",
    "ConstraintViolationError",
    "ReportStoreError",
]
