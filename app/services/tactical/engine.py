"""Live tactical engine: applies the configured rule to the watchlist and
trades the tactical paper book — no LLM anywhere in this path.

Universe is controlled by ``TACTICAL_UNIVERSE`` and defaults to "all", i.e.
the SAME pool the LLM sees. That is a fairness choice, not a profit one:
with the rule restricted to 7 US large caps and the LLM seeing 25 names, a
divergence between the two books could not be attributed to the engine rather
than the universe. Measured on the screener picks the rule returns Sharpe 0.25
against 0.33 for a zero-skill exposure-matched blend — it loses there exactly
as it loses on large caps.

DISABLED BY DEFAULT (``tactical_rule`` empty): the 10-year backtest
(scripts/backtest_tactical.py) showed none of the rule library beating
buy-and-hold risk-adjusted on this universe — 0/9 wins per rule. What
trend-following DID show is its textbook property: roughly half the drawdown
of buy-and-hold at a lower return. Enabling it is therefore an explicit
defensive choice the user makes in .env (TACTICAL_RULE=trend_following),
never a default.

Risk rails, always on when enabled: fixed fractional sizing, a max-positions
cap, one position per symbol, long-only, no leverage, and a daily-loss
circuit breaker that blocks new entries (exits always allowed).
"""

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.domain import Market
from app.models.base import session_factory
from app.models.entities import Position, Trade
from app.repositories.portfolio import PortfolioRepository
from app.repositories.watchlist import WatchlistRepository
from app.services.books import BOOK_POSITION_TYPE, rule_for
from app.services.broker_rules import MIN_ORDER_USD, apply_cost, currency_for_market
from app.services.paper_broker import (
    _paper_sell,
    live_price,
    paper_equity_usd,
    usd_rate,
)
from app.services.tactical.rules import RULES
from app.services.volatility import daily_volatility_pct_sync, default_stop_pct

logger = logging.getLogger(__name__)

_HISTORY_DAYS = 420  # enough for SMA200 + a year of signal context


def _history_sync(symbol: str):
    import yfinance as yf

    from tradingagents.dataflows.symbol_utils import normalize_symbol

    df = yf.Ticker(normalize_symbol(symbol)).history(period=f"{_HISTORY_DAYS}d")
    return df if not df.empty else None


async def _universe(book: str = "tactical") -> list[tuple[str, str, str]]:
    """Candidate (symbol, market, category) triples the rule may trade.

    CORE_ETF is excluded. It is the book's cash-parking vehicle, and a symbol
    cannot coherently be both a rule bet and the place idle cash rests:

      - the sweep refuses to add core when a conviction position already owns
        the symbol (it would insert a duplicate row), so a rule position in SPY
        silently blocks the book from ever deploying — measured at 48% idle
        cash, which is precisely the drag the index core exists to remove;
      - and the return would be double-counted, once as rule performance and
        once as benchmark exposure, making the book uninterpretable against
        the very benchmark it is scored on.

    Excluding it keeps the book readable as "rule positions + benchmark core".
    """
    settings = get_settings()
    # THIS book's core ETF, not the global CORE_ETF setting. The tactical book
    # parks in VOO while the setting says SPY, so the old global lookup excluded
    # the wrong symbol: had VOO ever reached the watchlist, the rule could have
    # opened a VOO position, and get_position (scalar_one_or_none) would then
    # raise MultipleResultsFound against the sweep's own core row — permanently
    # blocking that book from deploying idle cash.
    from app.services.core_holding import core_etf_for

    core_etf = core_etf_for(book).strip().upper()
    scope = settings.tactical_universe.strip().lower()
    async with session_factory()() as session:
        rows = await WatchlistRepository(session).list_all()

    def in_scope(t) -> bool:
        if scope == "us_core":
            return t.market == Market.US.value and t.category == "core"
        if scope == "us_all":
            return t.market == Market.US.value
        return True  # "all" — the same pool the LLM sees

    return [
        (t.symbol, t.market, t.category)
        for t in rows
        if in_scope(t) and t.tier != "paused" and t.symbol.upper() != core_etf
    ]


async def _tactical_buy(
    symbol: str, rule: str, market: str, category: str, book: str = "tactical"
) -> str | None:
    """Open a rule position. ``market``/``category`` come from the watchlist row.

    They must not be assumed: once ``tactical_universe`` widens beyond US core,
    the book can hold ``.NS`` names priced in INR and crypto, and hardcoding
    USD/us would book an Indian fill at the wrong currency and undercharge its
    spread by 7x.

    ``book`` selects which rule arm is trading, so a second rule book shares
    this code rather than forking it.
    """
    position_type = BOOK_POSITION_TYPE[book]
    price = await live_price(symbol)
    equity = await paper_equity_usd(book)
    # isfinite, not just `is None`: yfinance hands back NaN for a symbol it
    # cannot price, and NaN reaches the INSERT as a NOT NULL violation that
    # aborts the whole pass for this book (seen on AEGISVOPAK.NS, 2026-08-10).
    if price is None or equity is None:
        return None
    if not math.isfinite(price) or price <= 0 or not math.isfinite(equity):
        logger.warning("%s buy skipped for %s: unusable price/equity (%r/%r)",
                       book, symbol, price, equity)
        return None
    settings = get_settings()
    currency = currency_for_market(Market(market))
    rate = await usd_rate(currency)
    if rate is None or rate <= 0:
        logger.warning("Tactical buy skipped for %s: no FX rate for %s", symbol, currency)
        return None
    # A trend rule needs a WIDER stop than a volatility stop gives it. The
    # fixed 2.5x-vol stop fired on noise long before the trend broke, so both
    # 2026 stop-outs (AMZN, LLY) were re-entered higher days later and the
    # book closed two trades for two losses. The trailing stop starts wide and
    # ratchets up with price, which is what lets an exit land in profit.
    if settings.tactical_trailing_stop_enabled:
        stop = round(price * (1 - settings.tactical_trail_pct / 100), 4)
    else:
        vol = await asyncio.to_thread(daily_volatility_pct_sync, symbol)
        stop = round(price * (1 - default_stop_pct(vol) / 100), 4)

    from app.services.core_holding import ensure_cash

    # Re-check the skip conditions BEFORE liquidating core to fund the order:
    # funding a buy that is then skipped would leave the book in idle cash
    # until the next sweep. The authoritative checks still run in the
    # transaction below.
    alloc_target = equity * settings.tactical_size_pct
    async with session_factory()() as session:
        if await PortfolioRepository(session).get_position(position_type, symbol) is not None:
            return None
    if alloc_target >= MIN_ORDER_USD:
        await ensure_cash(book, alloc_target)

    async with session_factory()() as session, session.begin():
        repo = PortfolioRepository(session)
        account = await repo.get_account(book)
        if account is None:
            return None
        if await repo.get_position(position_type, symbol) is not None:
            return None
        alloc = min(equity * settings.tactical_size_pct, account.cash)
        if alloc < MIN_ORDER_USD:
            logger.info("%s buy skipped for %s: insufficient cash", book, symbol)
            return None
        # alloc is USD; quantity is in the instrument's own currency.
        quantity = (alloc * rate) / price
        fee = apply_cost(alloc, symbol, market, category)
        account.cash -= alloc + fee
        await repo.add_position(Position(
            account_type=position_type, symbol=symbol, market=market,
            currency=currency, quantity=quantity, avg_price=price, stop_loss=stop,
            note=f"rule {rule}",
        ))
        await repo.add_trade(Trade(
            account_type=position_type, symbol=symbol, side="buy",
            quantity=quantity, price=price, currency=currency,
            reason=f"tactical {rule}",
        ))
    return f"bought {quantity:.4f} {symbol} @ {price:,.2f} {currency} (≈${alloc:,.0f})"


async def _in_cooldown(symbol: str, days: int, book: str = "tactical") -> bool:
    """True when this symbol was sold from ``book`` within ``days``.

    Without this the rule re-buys whatever the stop just sold: in Jul 2026
    both AMZN and LLY were stopped out and re-entered within days at HIGHER
    prices, turning noise into realised losses on the round trip.

    Scoped per book, so one arm's stop-out does not block another arm's entry.
    """
    if days <= 0:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with session_factory()() as session:
        trades = await PortfolioRepository(session).list_trades(
            limit=500, account_type=BOOK_POSITION_TYPE[book]
        )
    for trade in trades:
        if trade.symbol != symbol or trade.side != "sell" or trade.executed_at is None:
            continue
        # Timestamps are stored naive UTC (see CLAUDE.md); make them aware to compare.
        executed = trade.executed_at
        if executed.tzinfo is None:
            executed = executed.replace(tzinfo=timezone.utc)
        if executed >= cutoff:
            return True
    return False


async def run_tactical(book: str = "tactical") -> list[str]:
    """One end-of-day pass for one rule arm. Returns action summaries.

    ``book`` selects the arm. Its rule is pinned in the book spec, falling back
    to TACTICAL_RULE for the original tactical book so that stays configurable.
    """
    settings = get_settings()
    position_type = BOOK_POSITION_TYPE[book]
    rule = rule_for(book, settings.tactical_rule.strip()).strip()
    if not rule:
        return []  # disabled — the backtest gate was not passed by default
    if rule not in RULES:
        logger.error("Unknown rule %r for %s; available: %s", rule, book, list(RULES))
        return []

    from app.services.core_holding import is_core
    from app.services.notifier import Notifier

    universe = await _universe(book)
    async with session_factory()() as session:
        repo = PortfolioRepository(session)
        # The index core is excluded: it is not a rule position. Counting it
        # would consume a max-positions seat, and — because the core ETF can
        # itself be a 'core'-category watchlist name and therefore in the
        # universe — a `signal == 0` on it would exit the benchmark.
        held = {
            p.symbol for p in await repo.list_positions(position_type) if not is_core(p)
        }

    # Daily-loss circuit breaker: compare live equity to today's snapshot.
    equity = await paper_equity_usd(book)
    block_entries = False
    if equity is not None:
        today = datetime.now(timezone.utc).date().isoformat()
        async with session_factory()() as session:
            snapshots = await PortfolioRepository(session).list_snapshots(book, limit=2)
        baseline = next(
            (s.equity_usd for s in snapshots if s.snapshot_date == today),
            snapshots[-1].equity_usd if snapshots else None,
        )
        if baseline and equity < baseline * (1 - settings.tactical_daily_loss_cap_pct / 100):
            block_entries = True
            logger.warning("%s circuit breaker: down >%s%% today — entries blocked",
                           book, settings.tactical_daily_loss_cap_pct)

    # Capital, not the counter, is the real ceiling: size_pct x max_positions
    # cannot exceed the investable fraction of equity. Past that point the
    # remaining slots either fill with sub-$50 dust or not at all, because
    # `alloc = min(equity * size_pct, account.cash)` silently shrinks as cash
    # depletes — so the configured diversification target is quietly missed.
    #
    # Clamped here rather than as an AssistantSettings validator on purpose:
    # that model is shared by every subsystem, so a cross-field validator would
    # turn a tactical-only misconfiguration into a startup crash for the whole
    # assistant service.
    investable_pct = 100.0 - settings.core_cash_buffer_pct
    capital_cap = max(1, int(investable_pct // (settings.tactical_size_pct * 100)))
    position_cap = min(settings.tactical_max_positions, capital_cap)
    if position_cap < settings.tactical_max_positions:
        logger.info(
            "Tactical cap clamped %d -> %d: %.0f%% investable at %.0f%% per position",
            settings.tactical_max_positions, position_cap,
            investable_pct, settings.tactical_size_pct * 100,
        )

    actions: list[str] = []
    for symbol, market, category in universe:
        df = await asyncio.to_thread(_history_sync, symbol)
        if df is None or len(df) < 260:
            continue
        try:
            signal = int(RULES[rule](df).iloc[-1])
        except Exception:
            logger.warning("Tactical signal failed for %s", symbol)
            continue

        if signal == 1 and symbol not in held:
            if block_entries or len(held) >= position_cap:
                continue
            if await _in_cooldown(symbol, settings.tactical_reentry_cooldown_days, book):
                logger.info("%s entry for %s suppressed: re-entry cooldown", book, symbol)
                continue
            summary = await _tactical_buy(symbol, rule, market, category, book)
            if summary:
                held.add(symbol)
                actions.append(summary)
        elif signal == 0 and symbol in held:
            summary = await _paper_sell(
                symbol, "all", reason=f"tactical {rule} exit", book=book
            )
            if summary:
                held.discard(symbol)
                actions.append(summary)

    if actions:
        notifier = Notifier(settings)
        await notifier.send_telegram(
            f"⚡ <b>{book} ({rule})</b>\n" + "\n".join("· " + a for a in actions)
        )
    logger.info("%s pass done: %d action(s)", book, len(actions))
    return actions


async def run_all_tactical() -> list[str]:
    """Scheduler entry point: one pass per rule-driven arm.

    Each arm is isolated the same way sweep_all_books isolates the core sweep —
    one book raising must not stop the others from trading.
    """
    from app.services.books import BOOKS

    events: list[str] = []
    for label, book_spec in BOOKS.items():
        if not book_spec.rule_driven:
            continue
        try:
            events.extend(f"{label}: {a}" for a in await run_tactical(label))
        except Exception:
            logger.exception("Tactical pass failed for %s", label)
    return events


async def record_equity_snapshots() -> None:
    """Daily equity per book — the scoreboard's raw data. Cheap, always on."""
    today = datetime.now(timezone.utc).date().isoformat()
    from app.services.books import BOOKS

    recorded = 0
    for book in BOOKS:
        equity = await paper_equity_usd(book)
        # Per-book try/except AND an isfinite check: one book's bad price used to
        # raise on INSERT and abort the loop, so a single NaN cost EVERY book its
        # snapshot that day — i.e. a hole in the equity curve the scoreboard is
        # built on. One arm's data problem must not blind the others.
        if equity is None or not math.isfinite(equity):
            logger.error("No usable equity for %s; snapshot skipped", book)
            continue
        try:
            async with session_factory()() as session, session.begin():
                await PortfolioRepository(session).record_snapshot(book, today, equity)
            recorded += 1
        except Exception:
            logger.exception("Snapshot failed for %s", book)
    logger.info("Equity snapshots recorded for %s: %d/%d books", today, recorded, len(BOOKS))
