"""Domain exception hierarchy for the portfolio management package.

All exceptions raised by this package inherit from ``PortfolioError`` so that
callers can catch the entire family with a single ``except PortfolioError``.

Example::

    from tradingagents.portfolio.exceptions import (
        PortfolioError,
        InsufficientCashError,
    )

    try:
        repo.add_holding(pid, "AAPL", shares=100, price=195.50)
    except InsufficientCashError as e:
        print(f"Cannot buy: {e}")
    except PortfolioError as e:
        print(f"Unexpected portfolio error: {e}")
"""

from __future__ import annotations


class PortfolioError(Exception):
    """Base exception for all portfolio-management errors."""


class PortfolioNotFoundError(PortfolioError):
    """Raised when a requested portfolio_id does not exist in the database."""


class HoldingNotFoundError(PortfolioError):
    """Raised when a requested (portfolio_id, ticker) holding does not exist."""


class DuplicatePortfolioError(PortfolioError):
    """Raised when attempting to create a portfolio that already exists."""


class InsufficientCashError(PortfolioError):
    """Raised when a BUY order exceeds the portfolio's available cash balance."""


class InsufficientSharesError(PortfolioError):
    """Raised when a SELL order exceeds the number of shares held."""


class ConstraintViolationError(PortfolioError):
    """Raised when a trade would violate a PM constraint.

    Constraints enforced:
    - Max position size (default 15 % of portfolio value)
    - Max sector exposure (default 35 % of portfolio value)
    - Min cash reserve (default 5 % of portfolio value)
    - Max number of positions (default 15)
    """


class ReportStoreError(PortfolioError):
    """Raised on filesystem read/write failures in ReportStore."""
