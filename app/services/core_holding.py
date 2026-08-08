"""Index core: idle cash rests in the benchmark instead of in cash.

Why this exists
---------------
Against an SPY benchmark, an uninvested dollar is an unfunded short against
SPY — it forgoes the equity risk premium for certain. Over Jul-Aug 2026 the
strategic book ran 90.1% cash and the tactical book 47.7%, and both trailed
SPY despite the strategic book's picks returning +15.6% on the capital it
actually deployed.

The cash was not a sizing-table bug. Only 4 of 56 ratings were bullish, so
even doubling every allocation tier could not have deployed the book: there
was nothing to buy. Raising the tiers is therefore the wrong fix. Sweeping
idle cash into the benchmark routes around the rating distribution entirely.

This is the one change in the system that needs no forecasting edge to be
correct. Recovering ~85% of a book from 0% to the equity risk premium is an
accounting identity, not a prediction — and it is roughly an order of
magnitude larger than the entire selection-alpha budget the same research
put at +0.25 to +1.4pp/yr gross against 0.7-2.9pp/yr of costs.

How it works
------------
- ``sweep_idle_cash`` buys the core ETF with whatever sits above the cash
  buffer, so the resting state of uncommitted capital is "market return".
- ``ensure_cash`` sells just enough core to fund a satellite entry, so
  signals are never starved by a fully-invested core.
- Core positions carry ``note=CORE_NOTE`` so every other code path can tell
  a benchmark placeholder from a conviction position. Nothing else treats
  them specially: they mark to market, reconcile, and report like any other
  holding.

The core is deliberately *not* stop-lossed or target-sold. It is the
benchmark, not a bet — selling it on a drawdown would reintroduce exactly
the cash drag this module exists to remove.
"""

from __future__ import annotations

import logging
import time

from app.core.config import get_settings
from app.models.base import session_factory
from app.models.entities import Position, Trade
from app.repositories.portfolio import PortfolioRepository

logger = logging.getLogger(__name__)

#: Marker written to ``Position.note`` identifying a benchmark placeholder.
CORE_NOTE = "core"

#: (symbol, window) -> (verdict, fetched_monotonic). A 200-day average moves
#: once a day, but GET /portfolio asks for it on every 60s dashboard poll —
#: without this each poll costs a Yahoo request for a value that cannot have
#: changed. Short enough that the pre-close sweep still sees a fresh read.
_TREND_CACHE: dict[tuple[str, int], tuple[bool | None, float]] = {}
_TREND_TTL_SECONDS = 900


def is_core(position: Position) -> bool:
    """True when a position is the index core rather than a conviction bet."""
    return (position.note or "").strip().lower() == CORE_NOTE


async def _core_position(repo: PortfolioRepository, book: str, symbol: str) -> Position | None:
    from app.services.paper_broker import BOOK_POSITION_TYPE

    position = await repo.get_position(BOOK_POSITION_TYPE[book], symbol)
    return position if position is not None and is_core(position) else None


def _trend_ok_sync(symbol: str, window: int) -> bool | None:
    """True when ``symbol`` closes above its ``window``-day average.

    Returns None when history is unavailable, and callers treat that as
    "stay invested" — an outage must never silently liquidate the book.
    """
    import yfinance as yf

    cached = _TREND_CACHE.get((symbol, window))
    if cached is not None and time.monotonic() - cached[1] < _TREND_TTL_SECONDS:
        return cached[0]

    try:
        hist = yf.Ticker(symbol).history(period=f"{window + 60}d", auto_adjust=True)
    except Exception:
        logger.warning("Trend check failed for %s", symbol, exc_info=True)
        return None
    closes = hist.get("Close")
    if closes is None or len(closes) < window:
        return None
    verdict = float(closes.iloc[-1]) > float(closes.iloc[-window:].mean())
    _TREND_CACHE[(symbol, window)] = (verdict, time.monotonic())
    return verdict


async def core_trend_ok(book: str = "strategic") -> bool:
    """Whether ``book`` may hold its core now. True when its filter is off."""
    import asyncio

    from app.services.books import spec

    settings = get_settings()
    sp = spec(book)
    # A book's own spec decides its ETF and filter; the global setting only
    # gates the strategic/tactical arms so existing config keeps working.
    trend_on = sp.trend_filter or (sp.active and settings.core_trend_filter)
    if not trend_on:
        return True
    etf = core_etf_for(book)
    ok = await asyncio.to_thread(_trend_ok_sync, etf, settings.core_trend_window)
    if ok is None:
        logger.warning("No trend data for %s; holding core", etf)
        return True
    return ok


def core_etf_for(book: str) -> str:
    """The ETF this book's idle cash rests in."""
    from app.services.books import spec

    # An empty spec ETF means "follow the CORE_ETF setting" (strategic only);
    # every other arm pins its own, because a passive control whose holding
    # could change under it is not a control.
    return spec(book).core_etf or get_settings().core_etf


async def _exit_core(book: str, reason: str) -> str | None:
    """Liquidate the core when the trend filter turns defensive."""
    from app.services.paper_broker import BOOK_POSITION_TYPE, live_price

    etf = core_etf_for(book)
    price = await live_price(etf)
    if price is None:
        return None
    async with session_factory()() as session, session.begin():
        repo = PortfolioRepository(session)
        account = await repo.get_account(book)
        position = await _core_position(repo, book, etf)
        if account is None or position is None or position.quantity <= 0:
            return None
        quantity = position.quantity
        proceeds = quantity * price
        pnl = quantity * (price - position.avg_price)
        account.cash += proceeds
        await repo.remove_position(position)
        await repo.add_trade(Trade(
            account_type=BOOK_POSITION_TYPE[book], symbol=etf,
            side="sell", quantity=quantity, price=price, currency="USD",
            reason=reason, realized_pnl_usd=pnl,
        ))
    logger.info("Core exited (%s): %s", book, reason)
    return f"exited core {etf} @ {price:,.2f} ({reason})"


async def sweep_idle_cash(book: str = "strategic") -> str | None:
    """Invest cash above the buffer into the core ETF. Returns a summary or None.

    Idempotent and safe to run on every scheduler pass: it exits quietly when
    the book is already deployed, when the residual is below the minimum trade
    size, or when the core is disabled.
    """
    from app.services.paper_broker import BOOK_POSITION_TYPE, live_price, paper_equity_usd

    settings = get_settings()
    if not settings.core_enabled:
        return None

    symbol = core_etf_for(book)
    equity = await paper_equity_usd(book)
    price = await live_price(symbol)
    if equity is None or price is None or price <= 0:
        logger.warning("Core sweep skipped for %s: no equity or price for %s", book, symbol)
        return None

    # Trend filter: below the long-term average, stay in cash and liquidate any
    # core already held. This is the defensive half — it is what converts a
    # -46% drawdown into -12%, and it only earns that in a genuine crash.
    if not await core_trend_ok(book):
        return await _exit_core(
            book, f"{symbol} below {settings.core_trend_window}d average"
        )

    buffer_usd = equity * settings.core_cash_buffer_pct / 100.0

    async with session_factory()() as session, session.begin():
        repo = PortfolioRepository(session)
        account = await repo.get_account(book)
        if account is None:
            return None

        investable = account.cash - buffer_usd
        if investable < settings.core_min_trade_usd:
            return None

        # A conviction position already open on the core ETF (the LLM can rate
        # SPY, and it is on the watchlist) owns that (account_type, symbol)
        # slot. Adding a second row would make PortfolioRepository.get_position
        # — a scalar_one_or_none — raise MultipleResultsFound on every later
        # lookup, breaking buys, sells and the sweep itself for that book.
        existing_any = await repo.get_position(BOOK_POSITION_TYPE[book], symbol)
        if existing_any is not None and not is_core(existing_any):
            logger.warning(
                "Core sweep skipped for %s: %s is already held as a signal position",
                book, symbol,
            )
            return None

        # Even the core pays a spread; SPY/VOO are 2bps, not free.
        from app.services.broker_rules import apply_cost

        fee = apply_cost(investable, symbol, "us", "core")
        investable -= fee
        quantity = investable / price
        account.cash -= investable + fee

        existing = existing_any
        if existing is not None:
            # Weighted-average the cost basis so P&L stays honest across adds.
            total_qty = existing.quantity + quantity
            existing.avg_price = (
                existing.avg_price * existing.quantity + price * quantity
            ) / total_qty
            existing.quantity = total_qty
        else:
            await repo.add_position(Position(
                account_type=BOOK_POSITION_TYPE[book],
                symbol=symbol,
                market="us",
                currency="USD",
                quantity=quantity,
                avg_price=price,
                stop_loss=None,      # the benchmark is never stopped out
                price_target=None,
                note=CORE_NOTE,
            ))
        await repo.add_trade(Trade(
            account_type=BOOK_POSITION_TYPE[book], symbol=symbol, side="buy",
            quantity=quantity, price=price, currency="USD",
            reason="core sweep",
        ))

    logger.info("Core sweep (%s): deployed $%.0f into %s", book, investable, symbol)
    return f"swept ${investable:,.0f} idle cash into {symbol} @ {price:,.2f}"


async def ensure_cash(book: str, needed_usd: float) -> float:
    """Sell core to raise ``needed_usd``. Returns the cash actually freed.

    A satellite entry calls this before sizing so the core never blocks a
    signal. Selling only the shortfall keeps the rest of the book invested.
    """
    from app.services.paper_broker import BOOK_POSITION_TYPE, live_price

    settings = get_settings()
    if not settings.core_enabled or needed_usd <= 0:
        return 0.0

    symbol = core_etf_for(book)
    price = await live_price(symbol)
    if price is None or price <= 0:
        return 0.0

    async with session_factory()() as session, session.begin():
        repo = PortfolioRepository(session)
        account = await repo.get_account(book)
        if account is None:
            return 0.0
        shortfall = needed_usd - account.cash
        if shortfall <= 0:
            return 0.0

        position = await _core_position(repo, book, symbol)
        if position is None:
            return 0.0

        quantity = min(shortfall / price, position.quantity)
        proceeds = quantity * price
        if proceeds <= 0:
            return 0.0

        pnl = quantity * (price - position.avg_price)
        account.cash += proceeds
        position.quantity -= quantity
        if position.quantity * price < 1.0:
            await repo.remove_position(position)
        await repo.add_trade(Trade(
            account_type=BOOK_POSITION_TYPE[book], symbol=symbol, side="sell",
            quantity=quantity, price=price, currency="USD",
            reason="core sold to fund signal", realized_pnl_usd=pnl,
        ))

    logger.info("Core funded $%.0f for a %s signal", proceeds, book)
    return proceeds


async def sweep_all_books() -> list[str]:
    """Sweep every book. Scheduler entry point."""
    from app.services.books import BOOKS

    events: list[str] = []
    for book in BOOKS:
        try:
            summary = await sweep_idle_cash(book)
        except Exception:  # one book's failure must not stop the other
            logger.exception("Core sweep failed for %s", book)
            continue
        if summary:
            events.append(f"{book}: {summary}")
    if events:
        logger.info("Core sweep: %s", "; ".join(events))
    return events

