"""Unified data-access facade for the Portfolio Manager.

``PortfolioRepository`` combines ``SupabaseClient`` (transactional data) and
``ReportStore`` (filesystem documents) into a single, business-logic-aware
interface.

Usage::

    from tradingagents.portfolio import PortfolioRepository

    repo = PortfolioRepository()
    portfolio = repo.create_portfolio("Main Portfolio", initial_cash=100_000.0)
    holding = repo.add_holding(portfolio.portfolio_id, "AAPL", shares=50, price=195.50)

See ``docs/portfolio/04_repository_api.md`` for full API documentation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tradingagents.portfolio.config import get_portfolio_config
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
    """Unified facade over SupabaseClient and ReportStore.

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
        self._cfg = config or get_portfolio_config()
        self._client = client or SupabaseClient.get_instance()
        self._store = store or ReportStore(base_dir=self._cfg["data_dir"])

    # ------------------------------------------------------------------
    # Portfolio lifecycle
    # ------------------------------------------------------------------

    def create_portfolio(
        self,
        name: str,
        initial_cash: float,
        currency: str = "USD",
    ) -> Portfolio:
        """Create a new portfolio with the given starting capital."""
        if initial_cash <= 0:
            raise ValueError(f"initial_cash must be > 0, got {initial_cash}")
        portfolio = Portfolio(
            portfolio_id=str(uuid.uuid4()),
            name=name,
            cash=initial_cash,
            initial_cash=initial_cash,
            currency=currency,
        )
        return self._client.create_portfolio(portfolio)

    def get_portfolio(self, portfolio_id: str) -> Portfolio:
        """Fetch a portfolio by ID."""
        return self._client.get_portfolio(portfolio_id)

    def get_portfolio_with_holdings(
        self,
        portfolio_id: str,
        prices: dict[str, float] | None = None,
    ) -> tuple[Portfolio, list[Holding]]:
        """Fetch portfolio + all holdings, optionally enriched with current prices."""
        portfolio = self._client.get_portfolio(portfolio_id)
        holdings = self._client.list_holdings(portfolio_id)
        if prices:
            # First pass: compute equity for total_value
            equity = sum(
                prices.get(h.ticker, 0.0) * h.shares for h in holdings
            )
            total_value = portfolio.cash + equity
            # Second pass: enrich each holding with weight
            for h in holdings:
                if h.ticker in prices:
                    h.enrich(prices[h.ticker], total_value)
            portfolio.enrich(holdings)
        return portfolio, holdings

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
        """Buy shares and update portfolio cash and holdings."""
        if shares <= 0:
            raise ValueError(f"shares must be > 0, got {shares}")
        if price <= 0:
            raise ValueError(f"price must be > 0, got {price}")

        cost = shares * price
        portfolio = self._client.get_portfolio(portfolio_id)

        if portfolio.cash < cost:
            raise InsufficientCashError(
                f"Need ${cost:.2f} but only ${portfolio.cash:.2f} available"
            )

        # Check for existing holding to update avg cost
        existing = self._client.get_holding(portfolio_id, ticker)
        if existing:
            new_total_shares = existing.shares + shares
            new_avg_cost = (
                (existing.shares * existing.avg_cost + shares * price) / new_total_shares
            )
            existing.shares = new_total_shares
            existing.avg_cost = new_avg_cost
            if sector:
                existing.sector = sector
            if industry:
                existing.industry = industry
            holding = self._client.upsert_holding(existing)
        else:
            holding = Holding(
                holding_id=str(uuid.uuid4()),
                portfolio_id=portfolio_id,
                ticker=ticker.upper(),
                shares=shares,
                avg_cost=price,
                sector=sector,
                industry=industry,
            )
            holding = self._client.upsert_holding(holding)

        # Deduct cash
        portfolio.cash -= cost
        self._client.update_portfolio(portfolio)

        # Record trade
        trade = Trade(
            trade_id=str(uuid.uuid4()),
            portfolio_id=portfolio_id,
            ticker=ticker.upper(),
            action="BUY",
            shares=shares,
            price=price,
            total_value=cost,
            trade_date=datetime.now(timezone.utc).isoformat(),
            signal_source="pm_agent",
        )
        self._client.record_trade(trade)

        return holding

    def remove_holding(
        self,
        portfolio_id: str,
        ticker: str,
        shares: float,
        price: float,
    ) -> Holding | None:
        """Sell shares and update portfolio cash and holdings."""
        if shares <= 0:
            raise ValueError(f"shares must be > 0, got {shares}")
        if price <= 0:
            raise ValueError(f"price must be > 0, got {price}")

        existing = self._client.get_holding(portfolio_id, ticker)
        if not existing:
            raise HoldingNotFoundError(
                f"No holding for {ticker} in portfolio {portfolio_id}"
            )

        if existing.shares < shares:
            raise InsufficientSharesError(
                f"Hold {existing.shares} shares of {ticker}, cannot sell {shares}"
            )

        proceeds = shares * price
        portfolio = self._client.get_portfolio(portfolio_id)

        if existing.shares == shares:
            # Full sell — delete holding
            self._client.delete_holding(portfolio_id, ticker)
            result = None
        else:
            existing.shares -= shares
            result = self._client.upsert_holding(existing)

        # Credit cash
        portfolio.cash += proceeds
        self._client.update_portfolio(portfolio)

        # Record trade
        trade = Trade(
            trade_id=str(uuid.uuid4()),
            portfolio_id=portfolio_id,
            ticker=ticker.upper(),
            action="SELL",
            shares=shares,
            price=price,
            total_value=proceeds,
            trade_date=datetime.now(timezone.utc).isoformat(),
            signal_source="pm_agent",
        )
        self._client.record_trade(trade)

        return result


    def batch_remove_holdings(
        self,
        portfolio_id: str,
        sells: list[dict[str, Any]],
        trade_date: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Sell shares in batch and update portfolio cash and holdings.

        Args:
            portfolio_id: Portfolio ID.
            sells: List of dicts with keys 'ticker', 'shares', 'price', 'rationale'.
            trade_date: The date to record the trades.

        Returns:
            Tuple of (executed_trades, failed_trades).
        """
        executed_trades = []
        failed_trades = []

        if not sells:
            return executed_trades, failed_trades

        # Pre-fetch portfolio and holdings once
        portfolio = self._client.get_portfolio(portfolio_id)
        current_holdings = {h.ticker.upper(): h for h in self._client.list_holdings(portfolio_id)}

        holdings_to_upsert = {}
        tickers_to_delete = set()
        trades_to_record = []
        total_proceeds = 0.0

        for sell in sells:
            ticker = sell["ticker"]
            shares = sell["shares"]
            price = sell["price"]
            rationale = sell.get("rationale")

            existing = current_holdings.get(ticker.upper())
            if not existing:
                failed_trades.append({
                    "action": "SELL",
                    "ticker": ticker,
                    "reason": f"No holding for {ticker} in portfolio {portfolio_id}",
                })
                continue

            if existing.shares < shares:
                failed_trades.append({
                    "action": "SELL",
                    "ticker": ticker,
                    "reason": f"Hold {existing.shares} shares of {ticker}, cannot sell {shares}",
                })
                continue

            proceeds = shares * price
            total_proceeds += proceeds

            if existing.shares == shares:
                tickers_to_delete.add(ticker.upper())
                # If we previously marked it to upsert, remove it
                if ticker.upper() in holdings_to_upsert:
                    del holdings_to_upsert[ticker.upper()]
                # Remove from local tracking
                del current_holdings[ticker.upper()]
            else:
                existing.shares -= shares
                holdings_to_upsert[ticker.upper()] = existing

            trade = Trade(
                trade_id=str(uuid.uuid4()),
                portfolio_id=portfolio_id,
                ticker=ticker.upper(),
                action="SELL",
                shares=shares,
                price=price,
                total_value=proceeds,
                trade_date=trade_date,
                rationale=rationale,
                signal_source="pm_agent",
            )
            trades_to_record.append(trade)

            executed_trades.append({
                "action": "SELL",
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "rationale": rationale,
                "trade_date": trade_date,
            })

        if not executed_trades:
            return executed_trades, failed_trades

        try:
            # Apply database writes in batch
            if tickers_to_delete:
                self._client.batch_delete_holdings(portfolio_id, list(tickers_to_delete))
            if holdings_to_upsert:
                self._client.batch_upsert_holdings(list(holdings_to_upsert.values()))

            portfolio.cash += total_proceeds
            self._client.update_portfolio(portfolio)

            if trades_to_record:
                self._client.batch_record_trades(trades_to_record)
        except Exception as exc:
            raise PortfolioError(f"Batch write failed: {exc}") from exc

        return executed_trades, failed_trades

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def take_snapshot(
        self,
        portfolio_id: str,
        prices: dict[str, float],
    ) -> PortfolioSnapshot:
        """Take an immutable snapshot of the current portfolio state."""
        portfolio, holdings = self.get_portfolio_with_holdings(portfolio_id, prices)
        snapshot = PortfolioSnapshot(
            snapshot_id=str(uuid.uuid4()),
            portfolio_id=portfolio_id,
            snapshot_date=datetime.now(timezone.utc).isoformat(),
            total_value=portfolio.total_value or portfolio.cash,
            cash=portfolio.cash,
            equity_value=portfolio.equity_value or 0.0,
            num_positions=len(holdings),
            holdings_snapshot=[h.to_dict() for h in holdings],
        )
        return self._client.save_snapshot(snapshot)

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
        """Save a PM agent decision and update portfolio.report_path."""
        path = self._store.save_pm_decision(date, portfolio_id, decision, markdown)
        # Update portfolio report_path
        portfolio = self._client.get_portfolio(portfolio_id)
        portfolio.report_path = str(self._store._portfolio_dir(date))
        self._client.update_portfolio(portfolio)
        return path

    def load_pm_decision(
        self,
        portfolio_id: str,
        date: str,
    ) -> dict[str, Any] | None:
        """Load a PM decision JSON. Returns None if not found."""
        return self._store.load_pm_decision(date, portfolio_id)

    def save_risk_metrics(
        self,
        portfolio_id: str,
        date: str,
        metrics: dict[str, Any],
    ) -> Path:
        """Save risk computation results."""
        return self._store.save_risk_metrics(date, portfolio_id, metrics)

    def load_risk_metrics(
        self,
        portfolio_id: str,
        date: str,
    ) -> dict[str, Any] | None:
        """Load risk metrics. Returns None if not found."""
        return self._store.load_risk_metrics(date, portfolio_id)

    def save_execution_result(
        self,
        portfolio_id: str,
        date: str,
        result: dict[str, Any],
    ) -> Path:
        """Save trade execution results."""
        return self._store.save_execution_result(date, portfolio_id, result)

    def load_execution_result(
        self,
        portfolio_id: str,
        date: str,
    ) -> dict[str, Any] | None:
        """Load trade execution results. Returns None if not found."""
        return self._store.load_execution_result(date, portfolio_id)
