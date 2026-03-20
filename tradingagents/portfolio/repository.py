"""Unified data-access façade for the Portfolio Manager.

``PortfolioRepository`` combines ``SupabaseClient`` (transactional data) and
``ReportStore`` (filesystem documents) into a single, business-logic-aware
interface.

Callers should **only** interact with ``PortfolioRepository`` — do not use
``SupabaseClient`` or ``ReportStore`` directly from outside this package.

Usage::

    from tradingagents.portfolio import PortfolioRepository

    repo = PortfolioRepository()

    # Create a portfolio
    portfolio = repo.create_portfolio("Main Portfolio", initial_cash=100_000.0)

    # Buy shares
    holding = repo.add_holding(portfolio.portfolio_id, "AAPL", shares=50, price=195.50)

    # Sell shares
    repo.remove_holding(portfolio.portfolio_id, "AAPL", shares=25, price=200.00)

    # Snapshot
    snapshot = repo.take_snapshot(portfolio.portfolio_id, prices={"AAPL": 200.00})

See ``docs/portfolio/04_repository_api.md`` for full API documentation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tradingagents.portfolio.exceptions import (
    HoldingNotFoundError,
    InsufficientCashError,
    InsufficientSharesError,
)
from tradingagents.portfolio.models import (
    Holding,
    Portfolio,
    PortfolioSnapshot,
    Trade,
)
from tradingagents.portfolio.report_store import ReportStore
from tradingagents.portfolio.supabase_client import SupabaseClient


class PortfolioRepository:
    """Unified façade over SupabaseClient and ReportStore.

    Implements business logic for:
    - Average cost basis updates on repeated buys
    - Cash deduction / credit on trades
    - Constraint enforcement (cash, position size)
    - Snapshot management
    """

    def __init__(
        self,
        client: SupabaseClient | None = None,
        store: ReportStore | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the repository.

        Args:
            client: SupabaseClient instance. Uses ``SupabaseClient.get_instance()``
                    when None.
            store: ReportStore instance. Creates a default instance when None.
            config: Portfolio config dict. Uses ``get_portfolio_config()`` when None.
        """
        # TODO: implement — resolve defaults, store as self._client, self._store, self._cfg
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Portfolio lifecycle
    # ------------------------------------------------------------------

    def create_portfolio(
        self,
        name: str,
        initial_cash: float,
        currency: str = "USD",
    ) -> Portfolio:
        """Create a new portfolio with the given starting capital.

        Generates a UUID for ``portfolio_id``. Sets ``cash = initial_cash``.

        Args:
            name: Human-readable portfolio name.
            initial_cash: Starting capital in USD (or configured currency).
            currency: ISO 4217 currency code.

        Returns:
            Persisted Portfolio instance.

        Raises:
            DuplicatePortfolioError: If the name is already in use.
            ValueError: If ``initial_cash <= 0``.
        """
        # TODO: implement
        raise NotImplementedError

    def get_portfolio(self, portfolio_id: str) -> Portfolio:
        """Fetch a portfolio by ID.

        Args:
            portfolio_id: UUID of the target portfolio.

        Raises:
            PortfolioNotFoundError: If not found.
        """
        # TODO: implement
        raise NotImplementedError

    def get_portfolio_with_holdings(
        self,
        portfolio_id: str,
        prices: dict[str, float] | None = None,
    ) -> tuple[Portfolio, list[Holding]]:
        """Fetch portfolio + all holdings, optionally enriched with current prices.

        Args:
            portfolio_id: UUID of the target portfolio.
            prices: Optional ``{ticker: current_price}`` dict. When provided,
                    holdings are enriched and ``Portfolio.enrich()`` is called.

        Returns:
            ``(Portfolio, list[Holding])`` — enriched when prices are supplied.
        """
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Holdings management
    # ------------------------------------------------------------------

    def add_holding(
        self,
        portfolio_id: str,
        ticker: str,
        shares: float,
        price: float,
        sector: str | None = None,
        industry: str | None = None,
    ) -> Holding:
        """Buy shares and update portfolio cash and holdings.

        Business logic:
        - Raises ``InsufficientCashError`` if ``portfolio.cash < shares * price``
        - If holding already exists: updates ``avg_cost`` using weighted average
        - ``portfolio.cash -= shares * price``
        - Records a BUY trade automatically

        Avg cost formula::

            new_avg_cost = (old_shares * old_avg_cost + new_shares * price)
                           / (old_shares + new_shares)

        Args:
            portfolio_id: UUID of the target portfolio.
            ticker: Ticker symbol.
            shares: Number of shares to buy (must be > 0).
            price: Execution price per share.
            sector: Optional GICS sector name.
            industry: Optional GICS industry name.

        Returns:
            Updated or created Holding.

        Raises:
            InsufficientCashError: If cash would go negative.
            PortfolioNotFoundError: If portfolio_id does not exist.
            ValueError: If shares <= 0 or price <= 0.
        """
        # TODO: implement
        raise NotImplementedError

    def remove_holding(
        self,
        portfolio_id: str,
        ticker: str,
        shares: float,
        price: float,
    ) -> Holding | None:
        """Sell shares and update portfolio cash and holdings.

        Business logic:
        - Raises ``HoldingNotFoundError`` if no holding exists for ticker
        - Raises ``InsufficientSharesError`` if ``holding.shares < shares``
        - If ``shares == holding.shares``: deletes the holding row, returns None
        - Otherwise: decrements ``holding.shares`` (avg_cost unchanged on sell)
        - ``portfolio.cash += shares * price``
        - Records a SELL trade automatically

        Args:
            portfolio_id: UUID of the target portfolio.
            ticker: Ticker symbol.
            shares: Number of shares to sell (must be > 0).
            price: Execution price per share.

        Returns:
            Updated Holding, or None if the position was fully closed.

        Raises:
            HoldingNotFoundError: If no holding exists for this ticker.
            InsufficientSharesError: If holding.shares < shares.
            PortfolioNotFoundError: If portfolio_id does not exist.
            ValueError: If shares <= 0 or price <= 0.
        """
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def take_snapshot(
        self,
        portfolio_id: str,
        prices: dict[str, float],
    ) -> PortfolioSnapshot:
        """Take an immutable snapshot of the current portfolio state.

        Fetches all holdings, enriches them with ``prices``, computes
        ``total_value``, then persists via ``SupabaseClient.save_snapshot()``.

        Args:
            portfolio_id: UUID of the target portfolio.
            prices: ``{ticker: current_price}`` for all held tickers.

        Returns:
            Persisted PortfolioSnapshot.
        """
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Report convenience methods
    # ------------------------------------------------------------------

    def save_pm_decision(
        self,
        portfolio_id: str,
        date: str,
        decision: dict[str, Any],
        markdown: str | None = None,
    ) -> Path:
        """Save a PM agent decision and update portfolio.report_path.

        Delegates to ``ReportStore.save_pm_decision()`` then updates the
        ``portfolio.report_path`` column in Supabase to point to the daily
        portfolio directory.

        Args:
            portfolio_id: UUID of the target portfolio.
            date: ISO date string, e.g. ``"2026-03-20"``.
            decision: PM decision dict.
            markdown: Optional human-readable markdown version.

        Returns:
            Path of the written JSON file.
        """
        # TODO: implement
        raise NotImplementedError

    def load_pm_decision(
        self,
        portfolio_id: str,
        date: str,
    ) -> dict[str, Any] | None:
        """Load a PM decision JSON. Returns None if not found.

        Args:
            portfolio_id: UUID of the target portfolio.
            date: ISO date string.
        """
        # TODO: implement
        raise NotImplementedError

    def save_risk_metrics(
        self,
        portfolio_id: str,
        date: str,
        metrics: dict[str, Any],
    ) -> Path:
        """Save risk computation results. Delegates to ReportStore.

        Args:
            portfolio_id: UUID of the target portfolio.
            date: ISO date string.
            metrics: Risk metrics dict (Sharpe, Sortino, VaR, beta, etc.).

        Returns:
            Path of the written file.
        """
        # TODO: implement
        raise NotImplementedError

    def load_risk_metrics(
        self,
        portfolio_id: str,
        date: str,
    ) -> dict[str, Any] | None:
        """Load risk metrics. Returns None if not found.

        Args:
            portfolio_id: UUID of the target portfolio.
            date: ISO date string.
        """
        # TODO: implement
        raise NotImplementedError
