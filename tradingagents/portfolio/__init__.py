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
from tradingagents.portfolio.risk_evaluator import (
    compute_returns,
    sharpe_ratio,
    sortino_ratio,
    value_at_risk,
    max_drawdown,
    beta,
    sector_concentration,
    compute_portfolio_risk,
    compute_holding_risk,
    check_constraints,
)
from tradingagents.portfolio.candidate_prioritizer import (
    score_candidate,
    prioritize_candidates,
)
from tradingagents.portfolio.trade_executor import TradeExecutor

__all__ = [
    # Models
    "Portfolio",
    "Holding",
    "Trade",
    "PortfolioSnapshot",
    # Repository (primary interface)
    "PortfolioRepository",
    # Risk evaluator functions
    "compute_returns",
    "sharpe_ratio",
    "sortino_ratio",
    "value_at_risk",
    "max_drawdown",
    "beta",
    "sector_concentration",
    "compute_portfolio_risk",
    "compute_holding_risk",
    "check_constraints",
    # Candidate prioritizer functions
    "score_candidate",
    "prioritize_candidates",
    # Trade executor
    "TradeExecutor",
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
