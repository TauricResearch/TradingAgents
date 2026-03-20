"""Supabase database client for the Portfolio Manager.

Thin wrapper around ``supabase-py`` that:
- Provides a singleton connection (one client per process)
- Translates Supabase / HTTP errors into domain exceptions
- Converts raw DB rows into typed model instances

Usage::

    from tradingagents.portfolio.supabase_client import SupabaseClient
    from tradingagents.portfolio.models import Portfolio

    client = SupabaseClient.get_instance()
    portfolio = client.get_portfolio("some-uuid")

Configuration (read from environment via ``get_portfolio_config()``):
    SUPABASE_URL — Supabase project URL
    SUPABASE_KEY — Supabase anon or service-role key
"""

from __future__ import annotations

from tradingagents.portfolio.exceptions import (
    DuplicatePortfolioError,
    HoldingNotFoundError,
    PortfolioNotFoundError,
)
from tradingagents.portfolio.models import (
    Holding,
    Portfolio,
    PortfolioSnapshot,
    Trade,
)


class SupabaseClient:
    """Singleton Supabase CRUD client for portfolio data.

    All public methods translate Supabase / HTTP errors into domain exceptions
    and return typed model instances.

    Do not instantiate directly — use ``SupabaseClient.get_instance()``.
    """

    _instance: "SupabaseClient | None" = None

    def __init__(self, url: str, key: str) -> None:
        """Initialise the Supabase client.

        Args:
            url: Supabase project URL.
            key: Supabase anon or service-role key.
        """
        # TODO: implement — create supabase.create_client(url, key)
        raise NotImplementedError

    @classmethod
    def get_instance(cls) -> "SupabaseClient":
        """Return the singleton instance, creating it if necessary.

        Reads SUPABASE_URL and SUPABASE_KEY from ``get_portfolio_config()``.

        Raises:
            PortfolioError: If SUPABASE_URL or SUPABASE_KEY are not configured.
        """
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Portfolio CRUD
    # ------------------------------------------------------------------

    def create_portfolio(self, portfolio: Portfolio) -> Portfolio:
        """Insert a new portfolio row.

        Args:
            portfolio: Portfolio instance with all required fields set.

        Returns:
            Portfolio with DB-assigned timestamps.

        Raises:
            DuplicatePortfolioError: If portfolio_id already exists.
        """
        # TODO: implement
        raise NotImplementedError

    def get_portfolio(self, portfolio_id: str) -> Portfolio:
        """Fetch a portfolio by ID.

        Args:
            portfolio_id: UUID of the target portfolio.

        Returns:
            Portfolio instance.

        Raises:
            PortfolioNotFoundError: If no portfolio has that ID.
        """
        # TODO: implement
        raise NotImplementedError

    def list_portfolios(self) -> list[Portfolio]:
        """Return all portfolios ordered by created_at DESC."""
        # TODO: implement
        raise NotImplementedError

    def update_portfolio(self, portfolio: Portfolio) -> Portfolio:
        """Update mutable portfolio fields (cash, report_path, metadata).

        Args:
            portfolio: Portfolio with updated field values.

        Returns:
            Updated Portfolio with refreshed updated_at.

        Raises:
            PortfolioNotFoundError: If portfolio_id does not exist.
        """
        # TODO: implement
        raise NotImplementedError

    def delete_portfolio(self, portfolio_id: str) -> None:
        """Delete a portfolio and all associated data (CASCADE).

        Args:
            portfolio_id: UUID of the portfolio to delete.

        Raises:
            PortfolioNotFoundError: If portfolio_id does not exist.
        """
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Holdings CRUD
    # ------------------------------------------------------------------

    def upsert_holding(self, holding: Holding) -> Holding:
        """Insert or update a holding row (upsert on portfolio_id + ticker).

        Args:
            holding: Holding instance with all required fields set.

        Returns:
            Holding with DB-assigned / refreshed timestamps.
        """
        # TODO: implement
        raise NotImplementedError

    def get_holding(self, portfolio_id: str, ticker: str) -> Holding | None:
        """Return the holding for (portfolio_id, ticker), or None if not found.

        Args:
            portfolio_id: UUID of the target portfolio.
            ticker: Ticker symbol (case-insensitive, stored as uppercase).
        """
        # TODO: implement
        raise NotImplementedError

    def list_holdings(self, portfolio_id: str) -> list[Holding]:
        """Return all holdings for a portfolio ordered by cost_basis DESC.

        Args:
            portfolio_id: UUID of the target portfolio.
        """
        # TODO: implement
        raise NotImplementedError

    def delete_holding(self, portfolio_id: str, ticker: str) -> None:
        """Delete the holding for (portfolio_id, ticker).

        Args:
            portfolio_id: UUID of the target portfolio.
            ticker: Ticker symbol.

        Raises:
            HoldingNotFoundError: If no such holding exists.
        """
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    def record_trade(self, trade: Trade) -> Trade:
        """Insert a new trade record. Immutable — no update method.

        Args:
            trade: Trade instance with all required fields set.

        Returns:
            Trade with DB-assigned trade_id and trade_date.
        """
        # TODO: implement
        raise NotImplementedError

    def list_trades(
        self,
        portfolio_id: str,
        ticker: str | None = None,
        limit: int = 100,
    ) -> list[Trade]:
        """Return recent trades for a portfolio, newest first.

        Args:
            portfolio_id: Filter by portfolio.
            ticker: Optional additional filter by ticker symbol.
            limit: Maximum number of rows to return.
        """
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        """Insert a new immutable portfolio snapshot.

        Args:
            snapshot: PortfolioSnapshot with all required fields set.

        Returns:
            Snapshot with DB-assigned snapshot_id and snapshot_date.
        """
        # TODO: implement
        raise NotImplementedError

    def get_latest_snapshot(self, portfolio_id: str) -> PortfolioSnapshot | None:
        """Return the most recent snapshot for a portfolio, or None.

        Args:
            portfolio_id: UUID of the target portfolio.
        """
        # TODO: implement
        raise NotImplementedError

    def list_snapshots(
        self,
        portfolio_id: str,
        limit: int = 30,
    ) -> list[PortfolioSnapshot]:
        """Return snapshots newest-first up to limit.

        Args:
            portfolio_id: UUID of the target portfolio.
            limit: Maximum number of snapshots to return.
        """
        # TODO: implement
        raise NotImplementedError
