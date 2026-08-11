"""Portfolio endpoints: paper book snapshot, real-holdings CRUD, trade history.

All valuations use live market prices (yfinance) and the live USDINR rate for
Indian holdings — the same data the analysis engine sees.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AddHoldingRequest, PortfolioResponse, PositionItem, TradeItem
from app.domain import infer_market
from app.models.base import get_session
from app.models.entities import Position, Trade
from app.repositories.portfolio import PortfolioRepository
from app.services.broker_rules import currency_for_market
from app.services.paper_broker import _batch_prices_sync, live_price, usd_rate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["portfolio"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _to_item(
    position: Position, prices: dict[str, float] | None = None
) -> PositionItem:
    # ``prices`` comes from ONE batched Yahoo request covering every open
    # position. Falling back to the per-symbol fetch keeps single-position
    # callers working, but the dashboard must never take that path: at a
    # few-second refresh, one call per position is rate-limited within
    # minutes — and it would starve the stop monitor, which shares this cache.
    price = (
        prices.get(position.symbol)
        if prices is not None
        else await live_price(position.symbol)
    )
    rate = await usd_rate(position.currency)
    value = pnl = pct = None
    if price is not None and rate:
        value = position.quantity * price / rate
        pnl = position.quantity * (price - position.avg_price) / rate
        pct = (price - position.avg_price) / position.avg_price * 100
    return PositionItem(
        id=position.id,
        account_type=position.account_type,
        symbol=position.symbol,
        market=position.market,
        currency=position.currency,
        quantity=position.quantity,
        avg_price=position.avg_price,
        stop_loss=position.stop_loss,
        price_target=position.price_target,
        opened_at=position.opened_at,
        note=position.note,
        last_price=price,
        value_usd=value,
        pnl_usd=pnl,
        pnl_pct=pct,
    )


#: Benchmark is a daily-close figure, so refetching it on every dashboard poll
#: buys nothing and costs one Yahoo request per refresh.
_BENCH_CACHE: dict[str, tuple[float | None, float]] = {}
_BENCH_TTL_SECONDS = 300


async def _benchmark_return_pct(since: datetime) -> float | None:
    key = since.date().isoformat()
    cached = _BENCH_CACHE.get(key)
    if cached is not None and time.monotonic() - cached[1] < _BENCH_TTL_SECONDS:
        return cached[0]

    def fetch() -> float | None:
        import math

        import yfinance as yf

        history = yf.Ticker("SPY").history(start=since.date().isoformat())
        closes = history["Close"].dropna() if not history.empty else None
        if closes is None or len(closes) < 2:
            return None
        first, last = float(closes.iloc[0]), float(closes.iloc[-1])
        # NaN here would serialise as literal NaN — invalid JSON, so the whole
        # dashboard fails to parse rather than one number being wrong.
        if not (math.isfinite(first) and math.isfinite(last)) or first <= 0:
            return None
        return (last - first) / first * 100

    try:
        value = await asyncio.to_thread(fetch)
    except Exception:
        logger.exception("Benchmark fetch failed")
        value = None
    # Cached even when None: a failing fetch retried every few seconds is the
    # fastest way to earn a rate limit.
    _BENCH_CACHE[key] = (value, time.monotonic())
    return value


@router.get("/portfolio", response_model=PortfolioResponse)
async def portfolio(session: SessionDep) -> PortfolioResponse:
    from app.api.schemas import BookSummary
    from app.core.config import get_settings
    from app.services.core_holding import core_etf_for, core_trend_ok
    from app.services.paper_broker import BOOK_POSITION_TYPE

    repo = PortfolioRepository(session)
    positions = await repo.list_positions()
    prices = await asyncio.to_thread(
        _batch_prices_sync, sorted({p.symbol for p in positions})
    )
    items = [await _to_item(p, prices) for p in positions]
    real = [i for i in items if i.account_type == "real"]

    settings = get_settings()
    books: list[BookSummary] = []
    oldest_created = None
    from app.services.books import BOOKS, rule_for

    for label in BOOKS:
        account = await repo.get_account(label)
        if account is None:
            continue
        oldest_created = min(filter(None, [oldest_created, account.created_at]))
        position_type = BOOK_POSITION_TYPE[label]
        book_positions = [i for i in items if i.account_type == position_type]
        equity = None
        if all(i.value_usd is not None for i in book_positions):
            equity = account.cash + sum(i.value_usd for i in book_positions)
        return_pct = (
            (equity - account.starting_cash) / account.starting_cash * 100
            if equity is not None else None
        )
        invested_pct = None
        if equity:
            invested = sum(i.value_usd or 0.0 for i in book_positions)
            invested_pct = invested / equity * 100
        core_value = sum(
            i.value_usd or 0.0
            for i in book_positions
            if (i.note or "").strip().lower() == "core"
        )
        # Mark-to-market on everything still open. None (rather than 0.0) when a
        # price is missing, so a data outage reads as "unknown" instead of
        # "flat" — a book with a stale feed must not look break-even.
        # An empty book is 0.00, not unknown — only a missing price is unknown.
        unrealised = (
            sum(i.pnl_usd for i in book_positions)
            if all(i.pnl_usd is not None for i in book_positions)
            else None
        )
        # Realised P&L is invisible in a positions-only view, which is exactly
        # how a book showing five green positions can still be losing money.
        closed = [
            t for t in await repo.list_trades(limit=None, account_type=position_type)
            if t.side == "sell"
        ]
        # Pinned rule for the arms that have one, else the configured default.
        rule = rule_for(label, settings.tactical_rule).strip() if BOOKS[label].rule_driven else ""
        books.append(BookSummary(
            label=label,
            starting_cash_usd=account.starting_cash,
            cash_usd=account.cash,
            equity_usd=equity,
            return_pct=return_pct,
            positions=book_positions,
            enabled=(not BOOKS[label].rule_driven) or bool(rule),
            core_etf=core_etf_for(label),
            description=BOOKS[label].description,
            rule=rule,
            active=BOOKS[label].active,
            invested_pct=invested_pct,
            core_value_usd=core_value,
            realised_pnl_usd=sum(t.realized_pnl_usd or 0.0 for t in closed),
            closed_trades=len(closed),
            winning_trades=sum(1 for t in closed if (t.realized_pnl_usd or 0) > 0),
            unrealised_pnl_usd=unrealised,
            open_positions=len(book_positions),
        ))
    if not books:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No paper books yet")

    strategic = next((b for b in books if b.label == "strategic"), books[0])
    return PortfolioResponse(
        books=books,
        real_positions=real,
        benchmark_return_pct=await _benchmark_return_pct(oldest_created),
        tactical_rule=settings.tactical_rule.strip(),
        core_etf=settings.core_etf,
        core_enabled=settings.core_enabled,
        core_trend_filter=settings.core_trend_filter,
        core_trend_window=settings.core_trend_window,
        core_defensive=(settings.core_trend_filter and not await core_trend_ok("strategic")),
        cash_usd=strategic.cash_usd,
        starting_cash_usd=strategic.starting_cash_usd,
        equity_usd=strategic.equity_usd,
        return_pct=strategic.return_pct,
        paper_positions=strategic.positions,
    )


@router.get("/portfolio/history")
async def portfolio_history(session: SessionDep) -> dict:
    """Daily equity curves per book, for the scoreboard sparklines."""
    from app.api.schemas import EquityPoint
    from app.services.books import BOOKS

    repo = PortfolioRepository(session)
    out: dict[str, list] = {}
    for book in BOOKS:
        snapshots = await repo.list_snapshots(book, limit=120)
        out[book] = [
            EquityPoint(date=s.snapshot_date, equity_usd=round(s.equity_usd, 2)).model_dump()
            for s in snapshots
        ]
    return out


@router.post("/holdings", response_model=PositionItem, status_code=status.HTTP_201_CREATED)
async def add_holding(body: AddHoldingRequest, session: SessionDep) -> PositionItem:
    """Log a real position you bought (shares, price, when)."""
    symbol = body.symbol.upper().strip()
    repo = PortfolioRepository(session)
    if await repo.get_position("real", symbol) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A real holding for {symbol} already exists — remove it first to re-enter",
        )
    market = infer_market(symbol)
    opened = (
        datetime.strptime(body.bought_at, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if body.bought_at else datetime.now(timezone.utc)
    )
    position = await repo.add_position(Position(
        account_type="real",
        symbol=symbol,
        market=market.value,
        currency=currency_for_market(market),
        quantity=body.quantity,
        avg_price=body.price,
        stop_loss=body.stop_loss,
        opened_at=opened,
        note=body.note,
    ))
    await repo.add_trade(Trade(
        account_type="real", symbol=symbol, side="buy",
        quantity=body.quantity, price=body.price,
        currency=position.currency, reason="manual entry",
        executed_at=opened,
    ))
    return await _to_item(position)


@router.delete("/holdings/{position_id}", response_model=TradeItem)
async def close_holding(position_id: int, session: SessionDep) -> TradeItem:
    """Remove a real holding (you sold it); logs the exit at the live price."""
    repo = PortfolioRepository(session)
    position = await repo.get_position_by_id(position_id)
    if position is None or position.account_type != "real":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    price = await live_price(position.symbol) or position.avg_price
    rate = await usd_rate(position.currency) or 1.0
    pnl = position.quantity * (price - position.avg_price) / rate
    trade = await repo.add_trade(Trade(
        account_type="real", symbol=position.symbol, side="sell",
        quantity=position.quantity, price=price, currency=position.currency,
        reason="manual close", realized_pnl_usd=pnl,
    ))
    await repo.remove_position(position)
    return TradeItem.model_validate(trade)


@router.get("/trades", response_model=list[TradeItem])
async def trades(session: SessionDep) -> list[TradeItem]:
    records = await PortfolioRepository(session).list_trades(limit=None)
    return [TradeItem.model_validate(t) for t in records]
