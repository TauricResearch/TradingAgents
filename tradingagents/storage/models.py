"""SQLAlchemy models for the trading agent persistence layer.

The schema is intentionally small for the first alpha: one coherent spine that
covers every logical area of the wiki design, so the rest of the system (graph,
agents, execution) has a frozen contract to read and write against. Tables grow
later; the boundaries do not.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Cross-cutting: instrument registry
# ---------------------------------------------------------------------------
class Instrument(Base):
    """Tradeable instrument (the investable universe + held tickers)."""

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    sector: Mapped[Optional[str]] = mapped_column(String(128), default=None)
    asset_type: Mapped[str] = mapped_column(String(32), default="stock")
    exchange: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    currency: Mapped[Optional[str]] = mapped_column(String(8), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Funnel: the persistent per-ticker "scheda"
# ---------------------------------------------------------------------------
class TickerCard(Base):
    """Persistent per-ticker card (parallelism-design B/C).

    Holds the cheap screening score (written by the deterministic screening
    module) and the latest synthesised evaluation (written by the deep-dive
    subgraph). The priority queue reads ``screening_score`` to decide which
    tickers deserve a deep dive. This is *not* the working ``research_state``:
    it is the durable summary that always lives in the DB.
    """

    __tablename__ = "ticker_card"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Screening (E) — written by the deterministic Quick Thinker
    screening_score: Mapped[Optional[float]] = mapped_column(Float, default=None)
    rank: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    last_screened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=None
    )
    screening_signals: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
    # Latest deep-dive evaluation — written by the PM after a deep dive (A)
    latest_direction: Mapped[Optional[str]] = mapped_column(String(16), default=None)
    latest_conviction: Mapped[Optional[str]] = mapped_column(String(16), default=None)
    latest_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
    next_check_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    in_portfolio: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ---------------------------------------------------------------------------
# Area: market_data (time-series) — TimescaleDB hypertable in production
# ---------------------------------------------------------------------------
class PriceBar(Base):
    """OHLCV bar. Carries the double date to prevent look-ahead bias.

    ``reference_date`` = the period the bar refers to; ``publication_date`` =
    when the datum became known to us. On PostgreSQL this table is promoted to
    a TimescaleDB hypertable on ``ts`` (see ``database.init_db``).
    """

    __tablename__ = "price_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "ts", "interval", name="uq_price_bar"),
        Index("ix_price_bars_symbol_ts", "symbol", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    interval: Mapped[str] = mapped_column(String(8), default="1d")
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[Optional[float]] = mapped_column(Float, default=None)
    vendor: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    reference_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    publication_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Area: market_data — news (for the Market/Sentiment desks)
# ---------------------------------------------------------------------------
class NewsItem(Base):
    """A news/headline item for a ticker, with double date + optional sentiment."""

    __tablename__ = "news_items"
    __table_args__ = (
        Index("ix_news_symbol_ts", "symbol", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    headline: Mapped[str] = mapped_column(String(512))
    summary: Mapped[Optional[str]] = mapped_column(String(2048), default=None)
    source: Mapped[Optional[str]] = mapped_column(String(128), default=None)
    url: Mapped[Optional[str]] = mapped_column(String(1024), default=None)
    sentiment: Mapped[Optional[float]] = mapped_column(Float, default=None)
    dedup_key: Mapped[str] = mapped_column(String(512), index=True)
    vendor: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    reference_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    publication_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Area: market_data — macro series (FRED), for the Market desk
# ---------------------------------------------------------------------------
class MacroPoint(Base):
    """One observation of a macro series (e.g. CPI, fed funds), double-dated."""

    __tablename__ = "macro_points"
    __table_args__ = (
        UniqueConstraint("series_id", "ts", name="uq_macro_point"),
        Index("ix_macro_series_ts", "series_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[str] = mapped_column(String(32), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value: Mapped[float] = mapped_column(Float)
    vendor: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    reference_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    publication_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Area: market_data — fundamentals snapshot (for the Fundamentals desk)
# ---------------------------------------------------------------------------
class FundamentalSnapshot(Base):
    """Point-in-time fundamentals/valuation metrics for a ticker."""

    __tablename__ = "fundamental_snapshots"
    __table_args__ = (
        Index("ix_fundamentals_symbol_asof", "symbol", "as_of"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    as_of: Mapped[Optional[date]] = mapped_column(Date, default=None)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    vendor: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    publication_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Area: tesi — sealed research_state / investment_state (Opzione C → JSON)
# ---------------------------------------------------------------------------
class ResearchState(Base):
    """Sealed investment thesis persisted as a JSON document.

    At runtime the state works flat; at sealing it is structured and written
    here (``payload``). The key decision fields are also promoted to columns so
    they can be filtered without parsing the JSON.
    """

    __tablename__ = "research_states"
    __table_args__ = (
        Index("ix_research_states_symbol_created", "symbol", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    as_of: Mapped[Optional[date]] = mapped_column(Date, default=None)
    version: Mapped[str] = mapped_column(String(16), default="alpha")
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft/complete/approved/declined
    direction: Mapped[Optional[str]] = mapped_column(String(16), default=None)
    conviction: Mapped[Optional[str]] = mapped_column(String(16), default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Area: rendicontazione (portfolio_state)
# ---------------------------------------------------------------------------
class PortfolioSnapshot(Base):
    """Point-in-time portfolio accounting snapshot (the ``inject_portfolio_state`` source)."""

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    cash: Mapped[float] = mapped_column(Float, default=0.0)
    total_value: Mapped[float] = mapped_column(Float, default=0.0)
    pnl: Mapped[Optional[float]] = mapped_column(Float, default=None)
    positions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Area: logs / trades (execution + audit)
# ---------------------------------------------------------------------------
class Trade(Base):
    """A trade the deterministic Trade function emitted / executed.

    ``client_order_id`` is the idempotency key (anti double-order) used during
    reconciliation; ``broker_order_id`` is the broker's id once confirmed.
    """

    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint("client_order_id", name="uq_trade_client_order_id"),
        Index("ix_trades_symbol_ts", "symbol", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    action: Mapped[str] = mapped_column(String(16))  # buy / sell / hold
    quantity: Mapped[Optional[float]] = mapped_column(Float, default=None)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, default=None)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, default=None)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/confirmed/cancelled
    commission: Mapped[Optional[float]] = mapped_column(Float, default=None)
    token_cost: Mapped[Optional[float]] = mapped_column(Float, default=None)
    client_order_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Area: costituzione / charter (Statuto)
# ---------------------------------------------------------------------------
class CharterRule(Base):
    """A deterministic Statute parameter (the textual charter -> parameter card).

    Stored as key -> JSON value so the Risk Analyst's deterministic guardrails
    read their thresholds from the DB rather than from hardcoded constants.
    """

    __tablename__ = "charter"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    description: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
