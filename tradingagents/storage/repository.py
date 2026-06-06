"""Typed access helpers over the storage models.

These functions are the *contract* the graph, agents and execution layer call
instead of touching the ORM directly. Each takes an explicit ``Session`` so the
caller owns the transaction boundary (use ``with get_session() as s: ...``).
Keeping the surface small and stable is what lets independent workstreams build
against the data layer in parallel without colliding.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    CharterRule,
    FundamentalSnapshot,
    Instrument,
    MacroPoint,
    NewsItem,
    PortfolioSnapshot,
    PriceBar,
    ResearchState,
    SocialPost,
    TickerCard,
    Trade,
)


# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------
def upsert_instrument(session: Session, symbol: str, **fields: Any) -> Instrument:
    inst = session.scalar(select(Instrument).where(Instrument.symbol == symbol))
    if inst is None:
        inst = Instrument(symbol=symbol, **fields)
        session.add(inst)
    else:
        for key, value in fields.items():
            setattr(inst, key, value)
    session.flush()
    return inst


# ---------------------------------------------------------------------------
# Ticker card (the funnel scheda)
# ---------------------------------------------------------------------------
def upsert_ticker_card(session: Session, symbol: str, **fields: Any) -> TickerCard:
    card = session.get(TickerCard, symbol)
    if card is None:
        card = TickerCard(symbol=symbol, **fields)
        session.add(card)
    else:
        for key, value in fields.items():
            setattr(card, key, value)
    session.flush()
    return card


def get_ticker_card(session: Session, symbol: str) -> Optional[TickerCard]:
    return session.get(TickerCard, symbol)


def top_screened(session: Session, limit: int = 10) -> list[TickerCard]:
    """Priority-queue read (D): highest screening_score first."""
    stmt = (
        select(TickerCard)
        .where(TickerCard.screening_score.is_not(None))
        .order_by(TickerCard.screening_score.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


# ---------------------------------------------------------------------------
# Research state (sealed thesis)
# ---------------------------------------------------------------------------
def save_research_state(
    session: Session,
    symbol: str,
    payload: dict[str, Any],
    *,
    direction: Optional[str] = None,
    conviction: Optional[str] = None,
    status: str = "draft",
    version: str = "alpha",
) -> ResearchState:
    state = ResearchState(
        symbol=symbol,
        payload=payload,
        direction=direction,
        conviction=conviction,
        status=status,
        version=version,
    )
    session.add(state)
    session.flush()
    return state


def latest_research_state(session: Session, symbol: str) -> Optional[ResearchState]:
    stmt = (
        select(ResearchState)
        .where(ResearchState.symbol == symbol)
        .order_by(ResearchState.created_at.desc(), ResearchState.id.desc())
        .limit(1)
    )
    return session.scalar(stmt)


# ---------------------------------------------------------------------------
# Market data (time-series)
# ---------------------------------------------------------------------------
def insert_price_bars(session: Session, symbol: str, bars: Iterable[dict[str, Any]]) -> int:
    """Bulk-insert OHLCV bars. Returns the number of rows added."""
    rows = [PriceBar(symbol=symbol, **bar) for bar in bars]
    session.add_all(rows)
    session.flush()
    return len(rows)


def existing_news_keys(session: Session, symbol: str) -> set[str]:
    """Dedup keys already stored for a symbol (DB-first news ingestion)."""
    return set(
        session.scalars(select(NewsItem.dedup_key).where(NewsItem.symbol == symbol))
    )


def insert_news_items(session: Session, symbol: str, items: Iterable[dict[str, Any]]) -> int:
    rows = [NewsItem(symbol=symbol, **item) for item in items]
    session.add_all(rows)
    session.flush()
    return len(rows)


def recent_news(session: Session, symbol: str, *, limit: int = 10) -> list[NewsItem]:
    stmt = (
        select(NewsItem)
        .where(NewsItem.symbol == symbol)
        .order_by(NewsItem.ts.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def existing_macro_ts(session: Session, series_id: str) -> set:
    return set(session.scalars(select(MacroPoint.ts).where(MacroPoint.series_id == series_id)))


def insert_macro_points(session: Session, series_id: str, points: Iterable[dict[str, Any]]) -> int:
    rows = [MacroPoint(series_id=series_id, **p) for p in points]
    session.add_all(rows)
    session.flush()
    return len(rows)


def latest_macro(session: Session, series_id: str) -> Optional[MacroPoint]:
    stmt = (
        select(MacroPoint)
        .where(MacroPoint.series_id == series_id)
        .order_by(MacroPoint.ts.desc())
        .limit(1)
    )
    return session.scalar(stmt)


def save_fundamentals(
    session: Session, symbol: str, metrics: dict[str, Any], *, as_of=None, vendor=None
) -> FundamentalSnapshot:
    snap = FundamentalSnapshot(symbol=symbol, metrics=metrics, as_of=as_of, vendor=vendor)
    session.add(snap)
    session.flush()
    return snap


def latest_fundamentals(session: Session, symbol: str) -> Optional[FundamentalSnapshot]:
    stmt = (
        select(FundamentalSnapshot)
        .where(FundamentalSnapshot.symbol == symbol)
        .order_by(FundamentalSnapshot.inserted_at.desc(), FundamentalSnapshot.id.desc())
        .limit(1)
    )
    return session.scalar(stmt)


def existing_social_keys(session: Session, symbol: str) -> set[str]:
    return set(session.scalars(select(SocialPost.dedup_key).where(SocialPost.symbol == symbol)))


def insert_social_posts(session: Session, symbol: str, items: Iterable[dict[str, Any]]) -> int:
    rows = [SocialPost(symbol=symbol, **it) for it in items]
    session.add_all(rows)
    session.flush()
    return len(rows)


def recent_social(session: Session, symbol: str, *, limit: int = 15) -> list[SocialPost]:
    stmt = (
        select(SocialPost)
        .where(SocialPost.symbol == symbol)
        .order_by(SocialPost.ts.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def latest_price(session: Session, symbol: str, interval: str = "1d") -> Optional[PriceBar]:
    stmt = (
        select(PriceBar)
        .where(PriceBar.symbol == symbol, PriceBar.interval == interval)
        .order_by(PriceBar.ts.desc())
        .limit(1)
    )
    return session.scalar(stmt)


# ---------------------------------------------------------------------------
# Portfolio accounting (rendicontazione)
# ---------------------------------------------------------------------------
def save_portfolio_snapshot(
    session: Session,
    *,
    cash: float,
    total_value: float,
    positions: Optional[list[dict[str, Any]]] = None,
    pnl: Optional[float] = None,
) -> PortfolioSnapshot:
    snap = PortfolioSnapshot(
        cash=cash,
        total_value=total_value,
        positions=positions or [],
        pnl=pnl,
    )
    session.add(snap)
    session.flush()
    return snap


def latest_portfolio_snapshot(session: Session) -> Optional[PortfolioSnapshot]:
    stmt = select(PortfolioSnapshot).order_by(PortfolioSnapshot.ts.desc()).limit(1)
    return session.scalar(stmt)


# ---------------------------------------------------------------------------
# Trades (logs / execution)
# ---------------------------------------------------------------------------
def record_trade(session: Session, symbol: str, action: str, **fields: Any) -> Trade:
    trade = Trade(symbol=symbol, action=action, **fields)
    session.add(trade)
    session.flush()
    return trade


def trade_by_client_order_id(session: Session, client_order_id: str) -> Optional[Trade]:
    """Idempotency lookup used during broker reconciliation."""
    return session.scalar(
        select(Trade).where(Trade.client_order_id == client_order_id)
    )


# ---------------------------------------------------------------------------
# Charter (Statuto parameters)
# ---------------------------------------------------------------------------
def set_charter_rule(
    session: Session, key: str, value: Any, description: Optional[str] = None
) -> CharterRule:
    rule = session.get(CharterRule, key)
    if rule is None:
        rule = CharterRule(key=key, value=value, description=description)
        session.add(rule)
    else:
        rule.value = value
        if description is not None:
            rule.description = description
        rule.updated_at = datetime.now(timezone.utc)
    session.flush()
    return rule


def get_charter_rule(session: Session, key: str, default: Any = None) -> Any:
    rule = session.get(CharterRule, key)
    return rule.value if rule is not None else default


def load_charter(session: Session) -> dict[str, Any]:
    """Load the whole Statute as a {key: value} dict (drives the Risk guardrails)."""
    return {r.key: r.value for r in session.scalars(select(CharterRule))}


# Default institutional-grade Statute (wiki). Numbers to be tuned in backtest.
DEFAULT_CHARTER: dict[str, Any] = {
    "min_risk_reward": 1.5,
    "max_position_pct": 0.10,
    "cash_reserve_pct": 0.10,
    "max_portfolio_var": 0.10,
    "base_risk_pct": 0.01,
    "heat_max_pct": 0.06,
}


def seed_default_charter(session: Session, overrides: Optional[dict[str, Any]] = None) -> None:
    """Insert the default Statute rules for any key not already present."""
    values = {**DEFAULT_CHARTER, **(overrides or {})}
    for key, value in values.items():
        if session.get(CharterRule, key) is None:
            set_charter_rule(session, key, value)
