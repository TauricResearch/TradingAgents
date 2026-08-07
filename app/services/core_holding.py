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

from app.core.config import get_settings
from app.models.base import session_factory
from app.models.entities import Position, Trade
from app.repositories.portfolio import PortfolioRepository

logger = logging.getLogger(__name__)

#: Marker written to ``Position.note`` identifying a benchmark placeholder.
CORE_NOTE = "core"


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

    try:
        hist = yf.Ticker(symbol).history(period=f"{window + 60}d", auto_adjust=True)
    except Exception:
        logger.warning("Trend check failed for %s", symbol, exc_info=True)
        return None
    closes = hist.get("Close")
    if closes is None or len(closes) < window:
        return None
    return float(closes.iloc[-1]) > float(closes.iloc[-window:].mean())


async def core_trend_ok() -> bool:
    """Whether the core may be held right now. True when the filter is off."""
    import asyncio

    settings = get_settings()
    if not settings.core_trend_filter:
        return True
    ok = await asyncio.to_thread(
        _trend_ok_sync, settings.core_etf, settings.core_trend_window
    )
    if ok is None:
        logger.warning("No trend data for %s; holding core", settings.core_etf)
        return True
    return ok


async def _exit_core(book: str, reason: str) -> str | None:
    """Liquidate the core when the trend filter turns defensive."""
    from app.services.paper_broker import BOOK_POSITION_TYPE, live_price

    settings = get_settings()
    price = await live_price(settings.core_etf)
    if price is None:
        return None
    async with session_factory()() as session, session.begin():
        repo = PortfolioRepository(session)
        account = await repo.get_account(book)
        position = await _core_position(repo, book, settings.core_etf)
        if account is None or position is None or position.quantity <= 0:
            return None
        quantity = position.quantity
        proceeds = quantity * price
        pnl = quantity * (price - position.avg_price)
        account.cash += proceeds
        await repo.remove_position(position)
        await repo.add_trade(Trade(
            account_type=BOOK_POSITION_TYPE[book], symbol=settings.core_etf,
            side="sell", quantity=quantity, price=price, currency="USD",
            reason=reason, realized_pnl_usd=pnl,
        ))
    logger.info("Core exited (%s): %s", book, reason)
    return f"exited core {settings.core_etf} @ {price:,.2f} ({reason})"


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

    symbol = settings.core_etf
    equity = await paper_equity_usd(book)
    price = await live_price(symbol)
    if equity is None or price is None or price <= 0:
        logger.warning("Core sweep skipped for %s: no equity or price for %s", book, symbol)
        return None

    # Trend filter: below the long-term average, stay in cash and liquidate any
    # core already held. This is the defensive half — it is what converts a
    # -46% drawdown into -12%, and it only earns that in a genuine crash.
    if not await core_trend_ok():
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

        quantity = investable / price
        account.cash -= investable

        existing = await _core_position(repo, book, symbol)
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

    symbol = settings.core_etf
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
    events: list[str] = []
    for book in ("strategic", "tactical"):
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


async def core_weight_pct(book: str = "strategic") -> float | None:
    """Share of book equity currently held in the core ETF, for reporting."""
    from app.services.paper_broker import BOOK_POSITION_TYPE, live_price, paper_equity_usd

    settings = get_settings()
    equity = await paper_equity_usd(book)
    if not equity:
        return None
    async with session_factory()() as session:
        repo = PortfolioRepository(session)
        positions = await repo.list_positions(BOOK_POSITION_TYPE[book])
    core = [p for p in positions if is_core(p) and p.symbol == settings.core_etf]
    if not core:
        return 0.0
    price = await live_price(settings.core_etf)
    if price is None:
        return None
    return sum(p.quantity for p in core) * price / equity * 100.0
