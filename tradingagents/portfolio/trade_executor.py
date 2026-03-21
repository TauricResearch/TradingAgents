"""Trade execution module for the Portfolio Manager.

Executes PM agent decisions by calling PortfolioRepository methods.
SELLs are always executed before BUYs to free up cash first.
All constraint checks happen before each BUY.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from tradingagents.portfolio.exceptions import (
    InsufficientCashError,
    PortfolioError,
)
from tradingagents.portfolio.risk_evaluator import check_constraints

logger = logging.getLogger(__name__)


class TradeExecutor:
    """Executes PM decisions against a PortfolioRepository.

    Args:
        repo: PortfolioRepository instance.  If None, a new instance is
              created on first use (requires a live DB connection).
        config: Portfolio config dict.  If None, defaults are used.
    """

    def __init__(self, repo=None, config: dict[str, Any] | None = None) -> None:
        self._repo = repo
        self._config = config or {}

    @property
    def repo(self):
        """Lazy-load repo if not provided at construction."""
        if self._repo is None:
            from tradingagents.portfolio.repository import PortfolioRepository

            self._repo = PortfolioRepository()
        return self._repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_decisions(
        self,
        portfolio_id: str,
        decisions: dict[str, Any],
        prices: dict[str, float],
        date: str | None = None,
    ) -> dict[str, Any]:
        """Execute a PM decision dict against the portfolio.

        SELLs are processed first (to free cash), then BUYs.  Each trade
        undergoes constraint pre-flight for BUYs.  Failures are caught
        gracefully and added to ``failed_trades``.

        Args:
            portfolio_id: The portfolio to trade against.
            decisions: Dict with ``sells`` and ``buys`` lists as produced by
                       the PM decision agent.
            prices: Current EOD prices (ticker → price).
            date: Trade date string (ISO).  Defaults to now (UTC).

        Returns:
            Dict with keys: executed_trades, failed_trades, snapshot, summary.
        """
        trade_date = date or datetime.now(timezone.utc).isoformat()
        executed_trades: list[dict[str, Any]] = []
        failed_trades: list[dict[str, Any]] = []

        sells = decisions.get("sells") or []
        buys = decisions.get("buys") or []

        # --- SELLs first (frees cash before BUYs; no constraint pre-flight for sells) ---
        sells_to_process = []
        for sell in sells:
            ticker = (sell.get("ticker") or "").upper()
            shares = float(sell.get("shares") or 0)
            rationale = sell.get("rationale") or ""

            if not ticker or shares <= 0:
                failed_trades.append({
                    "action": "SELL",
                    "ticker": ticker,
                    "reason": "Invalid ticker or shares",
                    "detail": str(sell),
                })
                continue

            price = prices.get(ticker)
            if price is None:
                failed_trades.append({
                    "action": "SELL",
                    "ticker": ticker,
                    "reason": f"No price found for {ticker}",
                })
                logger.warning("execute_decisions: no price for %s — skipping SELL", ticker)
                continue

            sells_to_process.append({
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "rationale": rationale,
            })

        if sells_to_process:
            try:
                executed, failed = self.repo.batch_remove_holdings(portfolio_id, sells_to_process, trade_date)
                executed_trades.extend(executed)
                for f in failed:
                    failed_trades.append({
                        "action": "SELL",
                        "ticker": f.get("ticker", "UNKNOWN"),
                        "reason": f.get("reason", "Batch execution failed"),
                    })
                    logger.warning("SELL failed for %s: %s", f.get("ticker"), f.get("reason"))
                for e in executed:
                    logger.info("SELL %s x %.2f @ %.2f", e["ticker"], e["shares"], e["price"])
            except PortfolioError as exc:
                logger.error("Batch sell execution failed: %s", exc)
                for s in sells_to_process:
                    failed_trades.append({
                        "action": "SELL",
                        "ticker": s["ticker"],
                        "reason": str(exc),
                    })

        # --- BUYs second ---
        for buy in buys:
            ticker = (buy.get("ticker") or "").upper()
            shares = float(buy.get("shares") or 0)
            sector = buy.get("sector")
            rationale = buy.get("rationale") or ""

            if not ticker or shares <= 0:
                failed_trades.append({
                    "action": "BUY",
                    "ticker": ticker,
                    "reason": "Invalid ticker or shares",
                    "detail": str(buy),
                })
                continue

            price = prices.get(ticker)
            if price is None:
                failed_trades.append({
                    "action": "BUY",
                    "ticker": ticker,
                    "reason": f"No price found for {ticker}",
                })
                logger.warning("execute_decisions: no price for %s — skipping BUY", ticker)
                continue

            # Pre-flight constraint check
            try:
                portfolio, holdings = self.repo.get_portfolio_with_holdings(
                    portfolio_id, prices
                )
            except PortfolioError as exc:
                failed_trades.append({
                    "action": "BUY",
                    "ticker": ticker,
                    "reason": f"Could not load portfolio: {exc}",
                })
                continue

            violations = check_constraints(
                portfolio,
                holdings,
                self._config,
                new_ticker=ticker,
                new_shares=shares,
                new_price=price,
                new_sector=sector,
            )
            if violations:
                failed_trades.append({
                    "action": "BUY",
                    "ticker": ticker,
                    "reason": "Constraint violation",
                    "violations": violations,
                })
                logger.warning("BUY %s rejected — constraints: %s", ticker, violations)
                continue

            try:
                self.repo.add_holding(
                    portfolio_id,
                    ticker,
                    shares,
                    price,
                    sector=sector,
                )
                executed_trades.append({
                    "action": "BUY",
                    "ticker": ticker,
                    "shares": shares,
                    "price": price,
                    "sector": sector,
                    "rationale": rationale,
                    "trade_date": trade_date,
                })
                logger.info("BUY %s x %.2f @ %.2f", ticker, shares, price)
            except (InsufficientCashError, PortfolioError) as exc:
                failed_trades.append({
                    "action": "BUY",
                    "ticker": ticker,
                    "reason": str(exc),
                })
                logger.warning("BUY failed for %s: %s", ticker, exc)

        # --- EOD snapshot ---
        try:
            snapshot = self.repo.take_snapshot(portfolio_id, prices)
            snapshot_dict = snapshot.to_dict()
        except PortfolioError as exc:
            snapshot_dict = {"error": str(exc)}
            logger.error("Snapshot failed: %s", exc)

        summary = {
            "executed": len(executed_trades),
            "failed": len(failed_trades),
            "total_attempted": len(sells) + len(buys),
        }

        return {
            "executed_trades": executed_trades,
            "failed_trades": failed_trades,
            "snapshot": snapshot_dict,
            "summary": summary,
        }
