"""Portfolio Manager — public package exports.

Import the primary interface classes from this package:

    from tradingagents.portfolio import (
        PortfolioRepository,
        Portfolio,
        Holding,
        Trade,
        PortfolioSnapshot,
        compute_risk_metrics,
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
from tradingagents.portfolio.risk_metrics import compute_risk_metrics

__all__ = [
    # Models
    "Portfolio",
    "Holding",
    "Trade",
    "PortfolioSnapshot",
    # Repository (primary interface)
    "PortfolioRepository",
    # Risk metrics computation
    "compute_risk_metrics",
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
