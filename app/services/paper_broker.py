"""The automatic paper broker: executes signals with virtual cash at live prices.

All prices are real market data (yfinance latest close/quote); INR books are
converted at the live USDINR rate. Execution is mechanical (see broker_rules)
so the portfolio's P&L measures the signals themselves.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from app.core.config import get_settings
from app.domain import Market
from app.models.base import session_factory
from app.models.entities import Position, Trade
from app.repositories.portfolio import PortfolioRepository
from app.services.broker_rules import (
    apply_cost,
    buy_quantity,
    currency_for_market,
    parse_level,
    sell_quantity,
)
from app.services.volatility import daily_volatility_pct_sync, default_stop_pct

logger = logging.getLogger(__name__)

# Reflex confirmation: a stop/target breach must PERSIST for a minimum window
# before acting, so one bad print can't trigger a sale. Time-based (not
# check-count-based) so the monitor cadence can change without weakening the
# whipsaw filter. In-memory is intentional — a restart just means
# re-confirming, which is the conservative direction.
_pending_breaches: dict[tuple[int, str], float] = {}  # (position_id, kind) -> first_seen_ts
_BREACH_CONFIRM_SECONDS = 180

_FX_CACHE: dict[str, tuple[float, float]] = {}  # currency -> (rate, fetched_monotonic)
_FX_TTL_SECONDS = 1800

# Last GOOD price per symbol. yfinance hiccups occasionally; a stale-but-real
# price beats a blank dashboard and a skipped monitor pass. Fresh fetches
# always overwrite it, so it only ever bridges gaps.
_PRICE_CACHE: dict[str, float] = {}


def _live_price_sync(symbol: str) -> float | None:
    """Latest traded price in the instrument's quote currency (real market data).

    Falls back to the last good price on a transient fetch failure so one
    yfinance hiccup doesn't blank the dashboard or skip a monitor pass.
    """
    import yfinance as yf

    from tradingagents.dataflows.symbol_utils import normalize_symbol

    try:
        history = yf.Ticker(normalize_symbol(symbol)).history(period="5d")
        if not history.empty:
            price = float(history["Close"].iloc[-1])
            _PRICE_CACHE[symbol] = price
            return price
    except Exception:
        logger.warning("Live price fetch failed for %s", symbol)
    cached = _PRICE_CACHE.get(symbol)
    if cached is not None:
        logger.info("Using last known price for %s: %.4f", symbol, cached)
    return cached


def _usd_rate_sync(currency: str) -> float | None:
    """Quote-currency units per USD, live via yfinance (cached ~30 min)."""
    if currency == "USD":
        return 1.0
    cached = _FX_CACHE.get(currency)
    if cached and time.monotonic() - cached[1] < _FX_TTL_SECONDS:
        return cached[0]
    import yfinance as yf

    try:
        history = yf.Ticker(f"USD{currency}=X").history(period="5d")
        if history.empty:
            return None
        rate = float(history["Close"].iloc[-1])
        _FX_CACHE[currency] = (rate, time.monotonic())
        return rate
    except Exception:
        logger.exception("FX rate fetch failed for %s", currency)
        return None


async def live_price(symbol: str) -> float | None:
    return await asyncio.to_thread(_live_price_sync, symbol)


async def usd_rate(currency: str) -> float | None:
    return await asyncio.to_thread(_usd_rate_sync, currency)


async def _position_value_usd(position: Position) -> float | None:
    price = await live_price(position.symbol)
    rate = await usd_rate(position.currency)
    if price is None or rate is None or rate <= 0:
        return None
    return position.quantity * price / rate


# Book label -> the account_type its positions/trades carry. Defined in
# app/services/books.py, which also holds each arm's core ETF and trend
# setting. Re-exported here because most call sites already import it.
from app.services.books import (  # noqa: E402
    AUTO_POSITION_TYPES,
    BOOK_POSITION_TYPE,
    POSITION_TYPE_BOOK,
    RULE_POSITION_TYPES,
)
from app.services.core_holding import is_core  # noqa: E402


async def paper_equity_usd(book: str = "strategic") -> float | None:
    """Cash plus live value of a book's open positions."""
    position_type = BOOK_POSITION_TYPE[book]
    async with session_factory()() as session:
        repo = PortfolioRepository(session)
        account = await repo.get_account(book)
        if account is None:
            return None
        positions = await repo.list_positions(position_type)
    total = account.cash
    for position in positions:
        value = await _position_value_usd(position)
        if value is None:
            logger.warning("No live value for %s; using cost basis", position.symbol)
            rate = await usd_rate(position.currency) or 1.0
            value = position.quantity * position.avg_price / rate
        total += value
    return total


async def execute_signal(
    symbol: str,
    market: Market,
    rating: str,
    decision_text: str | None,
    category: str = "satellite",
) -> str | None:
    """Apply one rating to the paper book. Returns a human summary or None.

    Buy/Overweight open a sized position (skipped if one is already open —
    the book is long-only, one position per symbol). Sell exits, Underweight
    trims half. Hold does nothing.
    """
    if rating in ("Buy", "Overweight"):
        return await _paper_buy(symbol, market, rating, decision_text, category)
    if rating in ("Sell", "Underweight"):
        return await _paper_sell(symbol, rating, reason=f"signal {rating}")
    return None


async def _paper_buy(
    symbol: str, market: Market, rating: str, decision_text: str | None, category: str
) -> str | None:
    currency = currency_for_market(market)
    price = await live_price(symbol)
    rate = await usd_rate(currency)
    equity = await paper_equity_usd()
    if price is None or rate is None or equity is None:
        logger.warning("Paper buy skipped for %s: no live price/FX", symbol)
        return None

    # Every position gets a stop: the analyst's when given, else a default
    # scaled to this ticker's own volatility (5-12% below entry).
    stop = parse_level(decision_text, "stop_loss")
    if stop is None or stop >= price:
        vol = await asyncio.to_thread(daily_volatility_pct_sync, symbol)
        stop = round(price * (1 - default_stop_pct(vol) / 100), 4)

    # With an index core, uncommitted capital is invested rather than idle, so
    # a signal must free its own funding first. Selling only the shortfall
    # keeps the rest of the book in the benchmark.
    #
    # Both skip conditions are re-checked here, BEFORE any core is liquidated:
    # funding an order that is then skipped would dump the core into idle cash
    # and leave it there until the next sweep — the exact drag the core exists
    # to remove. The authoritative checks still run inside the transaction.
    from app.services.broker_rules import BUY_ALLOCATION, MIN_ORDER_USD
    from app.services.core_holding import ensure_cash

    async with session_factory()() as session:
        if await PortfolioRepository(session).get_position("paper", symbol) is not None:
            logger.info("Paper book already holds %s; not adding on %s", symbol, rating)
            return None

    target_pct = BUY_ALLOCATION.get(category, BUY_ALLOCATION["satellite"]).get(rating, 0.0)
    if equity * target_pct >= MIN_ORDER_USD:
        await ensure_cash("strategic", equity * target_pct)

    async with session_factory()() as session, session.begin():
        repo = PortfolioRepository(session)
        account = await repo.get_account()
        if account is None:
            return None
        if await repo.get_position("paper", symbol) is not None:
            logger.info("Paper book already holds %s; not adding on %s", symbol, rating)
            return None
        quantity = buy_quantity(rating, equity, account.cash, price, rate, category)
        if quantity <= 0:
            logger.info("Paper buy skipped for %s: insufficient cash for a meaningful order", symbol)
            return None
        cost_usd = quantity * price / rate
        # Charge the spread. Without this the paper book reports gross returns
        # while the backtest gate charges 5bps, so the two are not comparable.
        fee = apply_cost(cost_usd, symbol, market.value, category)
        account.cash -= cost_usd + fee
        await repo.add_position(Position(
            account_type="paper",
            symbol=symbol,
            market=market.value,
            currency=currency,
            quantity=quantity,
            avg_price=price,
            stop_loss=stop,
            price_target=parse_level(decision_text, "price_target"),
        ))
        await repo.add_trade(Trade(
            account_type="paper", symbol=symbol, side="buy",
            quantity=quantity, price=price, currency=currency,
            reason=f"signal {rating}",
        ))
    pretty_qty = f"{quantity:.4f}".rstrip("0").rstrip(".")
    return (
        f"bought {pretty_qty} {symbol} @ {price:,.2f} {currency} "
        f"(≈${cost_usd:,.0f}, {rating})"
    )


def _category_of(position) -> str:
    """Cost tier for a held row: core placeholders and rule positions on the
    US large-cap set price as 'core'; screener picks price as 'satellite'."""
    from app.services.core_holding import is_core

    if is_core(position):
        return "core"
    return "core" if (position.note or "").startswith("rule ") else "satellite"


async def _paper_sell(
    symbol: str, rating_or_all: str, reason: str, book: str = "strategic"
) -> str | None:
    price = await live_price(symbol)
    if price is None:
        logger.warning("Paper sell skipped for %s: no live price", symbol)
        return None

    async with session_factory()() as session, session.begin():
        repo = PortfolioRepository(session)
        account = await repo.get_account(book)
        position = await repo.get_position(BOOK_POSITION_TYPE[book], symbol)
        if account is None or position is None:
            return None
        # The index core is the benchmark, not a bet: it is never stopped out,
        # target-sold, or exited on a rating. Only core_holding may sell it,
        # and only to fund a satellite entry. Without this guard a Sell rating
        # (or a rule exit) on CORE_ETF — which sits on the watchlist — would
        # liquidate the book back into the cash drag the core exists to remove.
        if is_core(position):
            logger.info("Refusing to sell the %s index core (%s): %s", book, symbol, reason)
            return None
        rate = await usd_rate(position.currency)
        if rate is None or rate <= 0:
            return None
        quantity = (
            position.quantity if rating_or_all == "all"
            else sell_quantity(rating_or_all, position.quantity)
        )
        if quantity <= 0:
            return None
        proceeds_usd = quantity * price / rate
        fee = apply_cost(proceeds_usd, symbol, position.market, _category_of(position))
        # P&L is net of the exit cost, so realised numbers are spendable ones.
        pnl_usd = quantity * (price - position.avg_price) / rate - fee
        account.cash += proceeds_usd - fee
        position.quantity -= quantity
        if position.quantity * price / rate < 1.0:  # fully (or effectively) closed
            await repo.remove_position(position)
        await repo.add_trade(Trade(
            account_type=BOOK_POSITION_TYPE[book], symbol=symbol, side="sell",
            quantity=quantity, price=price, currency=position.currency,
            reason=reason, realized_pnl_usd=pnl_usd,
        ))
    sign = "+" if pnl_usd >= 0 else "−"
    pretty_qty = f"{quantity:.4f}".rstrip("0").rstrip(".")
    return (
        f"sold {pretty_qty} {symbol} @ {price:,.2f} {position.currency} "
        f"(P&L {sign}${abs(pnl_usd):,.0f}, {reason})"
    )


async def _queue_post_mortem(symbol: str) -> None:
    """Mark the ticker due for immediate deep review (budget-governed)."""
    from app.repositories.watchlist import WatchlistRepository

    async with session_factory()() as session, session.begin():
        ticker = await WatchlistRepository(session).get_by_symbol(symbol)
        if ticker is not None:
            ticker.next_review_at = datetime.now(timezone.utc)


def _confirmed(pos_id: int, kind: str) -> bool:
    """True once a breach has persisted for the confirmation window."""
    key = (pos_id, kind)
    first_seen = _pending_breaches.get(key)
    if first_seen is None:
        _pending_breaches[key] = time.monotonic()
        return False
    if time.monotonic() - first_seen >= _BREACH_CONFIRM_SECONDS:
        del _pending_breaches[key]
        return True
    return False


def _batch_prices_sync(symbols: list[str]) -> dict[str, float]:
    """Latest prices for many symbols in ONE Yahoo request.

    This is what makes a fast monitor cadence rate-limit-safe: N positions
    cost one HTTP call per pass instead of N. Failures fall back to the
    per-symbol last-known-price cache.
    """
    import yfinance as yf

    from tradingagents.dataflows.symbol_utils import normalize_symbol

    if not symbols:
        return {}
    mapping = {normalize_symbol(s): s for s in symbols}
    prices: dict[str, float] = {}
    try:
        data = yf.download(
            list(mapping), period="1d", interval="1m",
            progress=False, group_by="ticker", threads=False,
        )
        for yahoo_symbol, original in mapping.items():
            try:
                closes = (
                    data[yahoo_symbol]["Close"] if len(mapping) > 1 else data["Close"]
                )
                closes = closes.dropna()
                if not closes.empty:
                    price = float(closes.iloc[-1])
                    prices[original] = price
                    _PRICE_CACHE[original] = price
            except (KeyError, TypeError, IndexError):
                continue
    except Exception:
        logger.warning("Batched price fetch failed for %d symbols", len(symbols))
    for symbol in symbols:
        if symbol not in prices and symbol in _PRICE_CACHE:
            prices[symbol] = _PRICE_CACHE[symbol]
    return prices


async def _ratchet_trailing_stops(
    snapshot: list[tuple], prices: dict[str, float]
) -> list[tuple]:
    """Raise trailing stops toward the high-water mark. Never lowers a stop.

    Rule-driven positions carry a trailing stop rather than a fixed one. A
    fixed volatility stop fights a trend rule — it fires on ordinary noise
    long before the trend actually breaks, so every exit realises a loss.
    Over Jul-Aug 2026 the tactical book closed two trades for two losses and
    re-entered both symbols *higher* within days.

    Ratcheting the stop upward as price advances keeps the downside guard
    while letting a winner run, which is what makes a profitable exit
    possible at all. The stop only ever moves up: a position that has run
    and pulled back exits at its protected level, not at entry.
    """
    settings = get_settings()
    if not settings.tactical_trailing_stop_enabled:
        return snapshot

    trail = settings.tactical_trail_pct / 100.0
    updates: dict[int, float] = {}
    for pos_id, account_type, symbol, stop, _target in snapshot:
        # Every rule-driven arm, not just the original tactical book — a second
        # rule arm with no ratchet would silently run fixed entry stops.
        if account_type not in RULE_POSITION_TYPES:
            continue
        price = prices.get(symbol)
        if price is None:
            continue
        candidate = round(price * (1 - trail), 4)
        if stop is None or candidate > stop:
            updates[pos_id] = candidate

    if not updates:
        return snapshot

    async with session_factory()() as session, session.begin():
        repo = PortfolioRepository(session)
        for pos_id, new_stop in updates.items():
            position = await repo.get_position_by_id(pos_id)
            if position is not None:
                logger.info(
                    "Trailing stop %s: %s -> %.2f",
                    position.symbol,
                    f"{position.stop_loss:.2f}" if position.stop_loss else "none",
                    new_stop,
                )
                position.stop_loss = new_stop

    return [
        (pid, at, sym, updates.get(pid, stop), tgt)
        for pid, at, sym, stop, tgt in snapshot
    ]


async def check_stops() -> list[str]:
    """Reflex layer (no LLM cost): watch every open position's stop and target.

    Paper positions act automatically — sell on a confirmed stop breach
    (damage control) or a confirmed target hit (disciplined profit-taking) —
    then queue a deep post-mortem to decide about re-entry. Real positions
    only alert (the stop is cleared so the alert fires once). Confirmation
    requires two consecutive monitor passes to avoid selling into one bad
    print.
    """
    from app.services.notifier import Notifier

    events: list[str] = []
    async with session_factory()() as session:
        positions = await PortfolioRepository(session).list_positions()
        # Index-core rows are excluded outright. They carry no stop or target
        # by construction, and leaving them in would let the trailing-stop
        # ratchet below WRITE one onto the tactical book's core and then
        # liquidate the benchmark on an ordinary 12% pullback.
        snapshot = [
            (p.id, p.account_type, p.symbol, p.stop_loss, p.price_target)
            for p in positions
            if not is_core(p)
        ]

    # One batched request reprices every open position per pass.
    prices = await asyncio.to_thread(
        _batch_prices_sync, sorted({s[2] for s in snapshot})
    )

    # Ratchet trailing stops up before testing breaches, so a winner that ran
    # today is protected at its new level rather than at its entry level.
    snapshot = await _ratchet_trailing_stops(snapshot, prices)

    live_ids = set()
    notifier = Notifier(get_settings())
    for pos_id, account_type, symbol, stop, target in snapshot:
        live_ids.add(pos_id)
        if not stop and not target:
            continue
        price = prices.get(symbol)
        if price is None:
            continue

        breach = None  # (kind, level)
        if stop and price <= stop:
            breach = ("stop-loss", stop)
        elif target and account_type in AUTO_POSITION_TYPES and price >= target:
            breach = ("target", target)
        if breach is None:
            _pending_breaches.pop((pos_id, "stop-loss"), None)
            _pending_breaches.pop((pos_id, "target"), None)
            continue

        kind, level = breach
        if not _confirmed(pos_id, kind):
            logger.info(
                "%s %s at %.2f crossed %s %.2f — awaiting confirmation",
                symbol, kind, price, kind, level,
            )
            continue

        if account_type in AUTO_POSITION_TYPES:
            book = POSITION_TYPE_BOOK[account_type]
            reason = f"{kind} {level:,.2f} hit"
            summary = await _paper_sell(symbol, "all", reason=reason, book=book)
            if summary:
                events.append(summary)
                emoji = "🛑" if kind == "stop-loss" else "🎯"
                await notifier.send_telegram(
                    f"{emoji} <b>{kind.capitalize()} hit</b> — {book} {summary}"
                )
                if book == "strategic":
                    await _queue_post_mortem(symbol)
        else:
            async with session_factory()() as session, session.begin():
                position = await PortfolioRepository(session).get_position_by_id(pos_id)
                if position is not None:
                    position.stop_loss = None
                    position.note = (
                        (position.note or "") + f" [stop {level:,.2f} hit "
                        f"{datetime.now(timezone.utc).date().isoformat()}]"
                    ).strip()
            events.append(f"real holding {symbol} breached stop {level:,.2f}")
            await notifier.send_telegram(
                f"🛑 <b>{symbol}</b> fell to {price:,.2f} — below your stop of "
                f"{level:,.2f}. Review your real position."
            )

    # Drop confirmation state for positions that no longer exist.
    for key in list(_pending_breaches):
        if key[0] not in live_ids:
            del _pending_breaches[key]

    if events:
        logger.info("Monitor events: %s", "; ".join(events))
    return events
