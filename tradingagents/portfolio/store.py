"""Portfolio store for persistent position and transaction data."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import Portfolio, PositionRecord, Transaction


class PortfolioStore:
    """Manages portfolio data persistence using a JSON file."""

    def __init__(self, portfolio_path: Optional[str] = None):
        """Initialize the portfolio store.
        
        Args:
            portfolio_path: Path to portfolio JSON file. 
                           Defaults to ~/.tradingagents/portfolio/portfolio.json
                           Can be overridden by TRADINGAGENTS_PORTFOLIO_PATH env var.
        """
        if portfolio_path:
            self._path = Path(portfolio_path)
        else:
            env_path = os.environ.get("TRADINGAGENTS_PORTFOLIO_PATH")
            if env_path:
                self._path = Path(env_path)
            else:
                self._path = Path.home() / ".tradingagents" / "portfolio" / "portfolio.json"
        
        self._ensure_dir()

    def _ensure_dir(self):
        """Ensure the portfolio directory exists."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Portfolio:
        """Load portfolio from disk."""
        if not self._path.exists():
            return Portfolio()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return Portfolio.model_validate(data)
        except (json.JSONDecodeError, Exception):
            return Portfolio()

    def _save(self, portfolio: Portfolio):
        """Save portfolio to disk."""
        portfolio.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._path.write_text(
            portfolio.model_dump_json(indent=2),
            encoding="utf-8"
        )

    # ─── Position CRUD ─────────────────────────────────────────

    def add_position(self, position: PositionRecord) -> None:
        """Add a new position to the portfolio."""
        portfolio = self._load()
        portfolio.positions.append(position)
        self._save(portfolio)

    def remove_position(self, ticker: str, entry_date: Optional[str] = None) -> bool:
        """Remove a position by ticker (and optionally entry_date).
        
        Returns True if a position was removed, False otherwise.
        """
        portfolio = self._load()
        original_count = len(portfolio.positions)
        if entry_date:
            portfolio.positions = [
                p for p in portfolio.positions
                if not (p.ticker.upper() == ticker.upper() and p.entry_date == entry_date)
            ]
        else:
            portfolio.positions = [
                p for p in portfolio.positions
                if p.ticker.upper() != ticker.upper()
            ]
        if len(portfolio.positions) < original_count:
            self._save(portfolio)
            return True
        return False

    def list_positions(self) -> List[PositionRecord]:
        """List all current positions."""
        return self._load().positions

    def get_position(self, ticker: str) -> List[PositionRecord]:
        """Get all positions for a specific ticker."""
        portfolio = self._load()
        return [p for p in portfolio.positions if p.ticker.upper() == ticker.upper()]

    # ─── Transaction CRUD ──────────────────────────────────────

    def add_transaction(self, transaction: Transaction) -> None:
        """Record a new transaction."""
        portfolio = self._load()
        portfolio.transactions.append(transaction)
        self._save(portfolio)

    def list_transactions(self, ticker: Optional[str] = None, limit: int = 20) -> List[Transaction]:
        """List transactions, optionally filtered by ticker.
        
        Args:
            ticker: If provided, only return transactions for this ticker.
            limit: Maximum number of transactions to return (most recent first).
        """
        portfolio = self._load()
        txs = portfolio.transactions
        if ticker:
            txs = [t for t in txs if t.ticker.upper() == ticker.upper()]
        # Sort by date descending, return most recent
        txs.sort(key=lambda t: t.date, reverse=True)
        return txs[:limit]

    # ─── Portfolio Queries ─────────────────────────────────────

    def get_portfolio(self) -> Portfolio:
        """Get the full portfolio object."""
        return self._load()

    def clear(self) -> None:
        """Clear all portfolio data."""
        self._save(Portfolio())

    @property
    def path(self) -> Path:
        """Return the portfolio file path."""
        return self._path
