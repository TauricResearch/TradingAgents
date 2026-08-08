"""ORM models for the assistant: watchlist membership and run/signal history.

Enum-like fields (market, tier, rating) are stored as plain strings — values
come from the ``app.domain`` enums — to keep SQLite schema evolution trivial.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WatchlistTicker(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    market: Mapped[str] = mapped_column(String(16), index=True)  # Market enum value
    asset_type: Mapped[str] = mapped_column(String(16), default="stock")
    tier: Mapped[str] = mapped_column(String(16), default="daily", index=True)  # Tier enum value
    added_by: Mapped[str] = mapped_column(String(16), default="manual")  # seed|manual|screener
    # core: permanent hand-picked holdings (giants, index ETFs) — never expire.
    # satellite: screener-sourced candidates — rotating tournament, can expire.
    category: Mapped[str] = mapped_column(String(16), default="satellite")
    consecutive_holds: Mapped[int] = mapped_column(Integer, default=0)
    last_rating: Mapped[str | None] = mapped_column(String(16), default=None)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # When the last analysis said it should be revisited (model-chosen date).
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ScheduleSlot(Base):
    """A configurable daily analysis window.

    Each slot fires at ``run_time`` in ``timezone`` and analyzes up to
    ``max_tickers`` of the stalest due watchlist tickers (optionally filtered
    to one market). Slot budgets exist because the LLM quota — not the
    watchlist size — is the scarce resource on free/cheap tiers.
    """

    __tablename__ = "schedule_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(64))
    run_time: Mapped[str] = mapped_column(String(5))  # "HH:MM" 24h
    timezone: Mapped[str] = mapped_column(String(64), default="America/Chicago")
    market: Mapped[str | None] = mapped_column(String(16), default=None)  # None = any market
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_tickers: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class PaperAccount(Base):
    """A virtual-cash book. Two live side by side:

    - ``strategic`` — trades LLM signals (positions carry account_type
      'paper' for backward compatibility)
    - ``tactical``  — trades the backtest-surviving rule (account_type
      'tactical')

    Cash is USD; positions in other currencies (INR for .NS) convert at the
    live FX rate for valuation and sizing.
    """

    __tablename__ = "paper_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(16), default="strategic")
    starting_cash: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EquitySnapshot(Base):
    """Daily equity per book — the raw material for the scoreboard's curves."""

    __tablename__ = "equity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book: Mapped[str] = mapped_column(String(16), index=True)
    snapshot_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD UTC
    equity_usd: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Position(Base):
    """An open holding — either the paper portfolio's or a real one the user logged.

    ``account_type`` separates the two books. Rows exist only while open; a
    full exit deletes the row (the trades table keeps the history).
    """

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # paper | tactical | real | one per core_* forward-test arm (see
    # app/services/books.py). Wide enough for 'core_trend'/'core_jepi' — SQLite
    # ignores VARCHAR length, but any other backend would reject them at 8.
    account_type: Mapped[str] = mapped_column(String(16), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(8), default="USD")  # quote currency
    quantity: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)  # in quote currency
    stop_loss: Mapped[float | None] = mapped_column(Float, default=None)
    price_target: Mapped[float | None] = mapped_column(Float, default=None)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    note: Mapped[str | None] = mapped_column(Text, default=None)


class Trade(Base):
    """Every executed buy/sell, paper and real — the immutable audit trail."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_type: Mapped[str] = mapped_column(String(16), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(4))  # buy | sell
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)  # in quote currency
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    reason: Mapped[str] = mapped_column(Text, default="")  # signal rating / stop-loss / manual
    realized_pnl_usd: Mapped[float | None] = mapped_column(Float, default=None)  # sells only
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class ScreenerResult(Base):
    """One scored candidate from a screener run (kept for the dashboard/audit)."""

    __tablename__ = "screener_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[str] = mapped_column(String(10), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(16))
    score: Mapped[float] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text, default="")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    added: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SignalRecord(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(16))
    trade_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD in market tz
    rating: Mapped[str | None] = mapped_column(String(16), default=None)
    prev_rating: Mapped[str | None] = mapped_column(String(16), default=None)
    changed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="success")  # success|error
    error: Mapped[str | None] = mapped_column(Text, default=None)
    report_path: Mapped[str | None] = mapped_column(Text, default=None)
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
