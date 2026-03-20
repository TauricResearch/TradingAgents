"""Data models for the Portfolio Manager Agent.

All models are Python ``dataclass`` types with:
- Full type annotations
- ``to_dict()`` for serialisation (JSON / Supabase)
- ``from_dict()`` class method for deserialisation
- ``enrich()`` for attaching runtime-computed fields

See ``docs/portfolio/02_data_models.md`` for full field specifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


@dataclass
class Portfolio:
    """A managed investment portfolio.

    Stored fields are persisted to Supabase. Computed fields (total_value,
    equity_value, cash_pct) are populated by ``enrich()`` and are *not*
    persisted.
    """

    portfolio_id: str
    name: str
    cash: float
    initial_cash: float
    currency: str = "USD"
    created_at: str = ""
    updated_at: str = ""
    report_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Runtime-computed (not stored in DB)
    total_value: float | None = field(default=None, repr=False)
    equity_value: float | None = field(default=None, repr=False)
    cash_pct: float | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialise stored fields to a flat dict for JSON / Supabase.

        Runtime-computed fields are excluded.
        """
        # TODO: implement
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Portfolio":
        """Deserialise from a DB row or JSON dict.

        Missing optional fields default gracefully. Extra keys are ignored.
        """
        # TODO: implement
        raise NotImplementedError

    def enrich(self, holdings: list["Holding"]) -> "Portfolio":
        """Compute total_value, equity_value, cash_pct from holdings.

        Modifies self in-place and returns self for chaining.

        Args:
            holdings: List of Holding objects with current_value populated
                      (i.e., ``holding.enrich()`` already called).
        """
        # TODO: implement
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Holding
# ---------------------------------------------------------------------------


@dataclass
class Holding:
    """An open position within a portfolio.

    Stored fields are persisted to Supabase. Runtime-computed fields
    (current_price, current_value, etc.) are populated by ``enrich()``.
    """

    holding_id: str
    portfolio_id: str
    ticker: str
    shares: float
    avg_cost: float
    sector: str | None = None
    industry: str | None = None
    created_at: str = ""
    updated_at: str = ""

    # Runtime-computed (not stored in DB)
    current_price: float | None = field(default=None, repr=False)
    current_value: float | None = field(default=None, repr=False)
    cost_basis: float | None = field(default=None, repr=False)
    unrealized_pnl: float | None = field(default=None, repr=False)
    unrealized_pnl_pct: float | None = field(default=None, repr=False)
    weight: float | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialise stored fields only (runtime-computed fields excluded)."""
        # TODO: implement
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Holding":
        """Deserialise from a DB row or JSON dict."""
        # TODO: implement
        raise NotImplementedError

    def enrich(self, current_price: float, portfolio_total_value: float) -> "Holding":
        """Populate runtime-computed fields in-place and return self.

        Formula:
            current_value      = current_price * shares
            cost_basis         = avg_cost * shares
            unrealized_pnl     = current_value - cost_basis
            unrealized_pnl_pct = unrealized_pnl / cost_basis  (0 when cost_basis == 0)
            weight             = current_value / portfolio_total_value  (0 when total == 0)

        Args:
            current_price: Latest market price for this ticker.
            portfolio_total_value: Total portfolio value (cash + equity).
        """
        # TODO: implement
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Trade
# ---------------------------------------------------------------------------


@dataclass
class Trade:
    """An immutable record of a single mock trade execution.

    Trades are never modified after creation.
    """

    trade_id: str
    portfolio_id: str
    ticker: str
    action: str  # "BUY" or "SELL"
    shares: float
    price: float
    total_value: float
    trade_date: str = ""
    rationale: str | None = None
    signal_source: str | None = None  # "scanner" | "holding_review" | "pm_agent"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise all fields."""
        # TODO: implement
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trade":
        """Deserialise from a DB row or JSON dict."""
        # TODO: implement
        raise NotImplementedError


# ---------------------------------------------------------------------------
# PortfolioSnapshot
# ---------------------------------------------------------------------------


@dataclass
class PortfolioSnapshot:
    """An immutable point-in-time snapshot of portfolio state.

    Taken after every trade execution session (Phase 5 of the PM workflow).
    Used for NAV time-series, performance attribution, and risk backtesting.
    """

    snapshot_id: str
    portfolio_id: str
    snapshot_date: str
    total_value: float
    cash: float
    equity_value: float
    num_positions: int
    holdings_snapshot: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise all fields. ``holdings_snapshot`` is already a list[dict]."""
        # TODO: implement
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PortfolioSnapshot":
        """Deserialise from DB row or JSON dict.

        ``holdings_snapshot`` is parsed from a JSON string when needed.
        """
        # TODO: implement
        raise NotImplementedError
