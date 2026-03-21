"""Data models for the Portfolio Manager Agent.

All models are Python ``dataclass`` types with:
- Full type annotations
- ``to_dict()`` for serialisation (JSON / Supabase)
- ``from_dict()`` class method for deserialisation
- ``enrich()`` for attaching runtime-computed fields

**float vs Decimal** — monetary fields (cash, price, shares, etc.) use plain
``float`` throughout.  Rationale:

1. This is **mock trading only** — no real money changes hands.  The cost of a
   subtle floating-point rounding error is zero.
2. All upstream data sources (yfinance, Alpha Vantage, Finnhub) return ``float``
   already.  Converting to ``Decimal`` at the boundary would require a custom
   JSON encoder *and* decoder everywhere, for no practical gain.
3. ``json.dumps`` serialises ``float`` natively; ``Decimal`` raises
   ``TypeError`` without a custom encoder.
4. If this ever becomes real-money trading, replace ``float`` with
   ``decimal.Decimal`` and add a ``DecimalEncoder`` — the interface is
   identical and the change is localised to this file.

See ``docs/portfolio/02_data_models.md`` for full field specifications.
"""

from __future__ import annotations

import json
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
        return {
            "portfolio_id": self.portfolio_id,
            "name": self.name,
            "cash": self.cash,
            "initial_cash": self.initial_cash,
            "currency": self.currency,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "report_path": self.report_path,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Portfolio":
        """Deserialise from a DB row or JSON dict.

        Missing optional fields default gracefully. Extra keys are ignored.
        """
        return cls(
            portfolio_id=data["portfolio_id"],
            name=data["name"],
            cash=float(data["cash"]),
            initial_cash=float(data["initial_cash"]),
            currency=data.get("currency", "USD"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            report_path=data.get("report_path"),
            metadata=data.get("metadata") or {},
        )

    def enrich(self, holdings: list["Holding"]) -> "Portfolio":
        """Compute total_value, equity_value, cash_pct from holdings.

        Modifies self in-place and returns self for chaining.

        Args:
            holdings: List of Holding objects with current_value populated
                      (i.e., ``holding.enrich()`` already called).
        """
        self.equity_value = sum(
            h.current_value for h in holdings if h.current_value is not None
        )
        self.total_value = self.cash + self.equity_value
        self.cash_pct = self.cash / self.total_value if self.total_value != 0.0 else 1.0
        return self


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
        return {
            "holding_id": self.holding_id,
            "portfolio_id": self.portfolio_id,
            "ticker": self.ticker,
            "shares": self.shares,
            "avg_cost": self.avg_cost,
            "sector": self.sector,
            "industry": self.industry,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Holding":
        """Deserialise from a DB row or JSON dict."""
        return cls(
            holding_id=data["holding_id"],
            portfolio_id=data["portfolio_id"],
            ticker=data["ticker"],
            shares=float(data["shares"]),
            avg_cost=float(data["avg_cost"]),
            sector=data.get("sector"),
            industry=data.get("industry"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

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
        self.current_price = current_price
        self.current_value = current_price * self.shares
        self.cost_basis = self.avg_cost * self.shares
        self.unrealized_pnl = self.current_value - self.cost_basis
        self.unrealized_pnl_pct = (
            self.unrealized_pnl / self.cost_basis if self.cost_basis != 0.0 else 0.0
        )
        self.weight = (
            self.current_value / portfolio_total_value if portfolio_total_value != 0.0 else 0.0
        )
        return self


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
        return {
            "trade_id": self.trade_id,
            "portfolio_id": self.portfolio_id,
            "ticker": self.ticker,
            "action": self.action,
            "shares": self.shares,
            "price": self.price,
            "total_value": self.total_value,
            "trade_date": self.trade_date,
            "rationale": self.rationale,
            "signal_source": self.signal_source,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trade":
        """Deserialise from a DB row or JSON dict."""
        return cls(
            trade_id=data["trade_id"],
            portfolio_id=data["portfolio_id"],
            ticker=data["ticker"],
            action=data["action"],
            shares=float(data["shares"]),
            price=float(data["price"]),
            total_value=float(data["total_value"]),
            trade_date=data.get("trade_date", ""),
            rationale=data.get("rationale"),
            signal_source=data.get("signal_source"),
            metadata=data.get("metadata") or {},
        )


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
    holdings_snapshot: list[dict[str, Any]] | str = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __getattribute__(self, name: str) -> Any:
        if name == "holdings_snapshot":
            val = object.__getattribute__(self, "holdings_snapshot")
            if isinstance(val, str):
                val = json.loads(val)
                object.__setattr__(self, "holdings_snapshot", val)
            return val
        return object.__getattribute__(self, name)

    def to_dict(self) -> dict[str, Any]:
        """Serialise all fields. ``holdings_snapshot`` is already a list[dict]."""
        return {
            "snapshot_id": self.snapshot_id,
            "portfolio_id": self.portfolio_id,
            "snapshot_date": self.snapshot_date,
            "total_value": self.total_value,
            "cash": self.cash,
            "equity_value": self.equity_value,
            "num_positions": self.num_positions,
            "holdings_snapshot": self.holdings_snapshot,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PortfolioSnapshot":
        """Deserialise from DB row or JSON dict.

        ``holdings_snapshot`` is parsed lazily on first access.
        """
        return cls(
            snapshot_id=data["snapshot_id"],
            portfolio_id=data["portfolio_id"],
            snapshot_date=data["snapshot_date"],
            total_value=float(data["total_value"]),
            cash=float(data["cash"]),
            equity_value=float(data["equity_value"]),
            num_positions=int(data["num_positions"]),
            holdings_snapshot=data.get("holdings_snapshot", []),
            metadata=data.get("metadata") or {},
        )
