"""Live tactical engine: applies the configured rule to the core US universe
and trades the tactical paper book — no LLM anywhere in this path.

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
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.domain import Market
from app.models.base import session_factory
from app.models.entities import Position, Trade
from app.repositories.portfolio import PortfolioRepository
from app.repositories.watchlist import WatchlistRepository
from app.services.paper_broker import _paper_sell, live_price, paper_equity_usd
from app.services.tactical.rules import RULES
from app.services.volatility import daily_volatility_pct_sync, default_stop_pct

logger = logging.getLogger(__name__)

_HISTORY_DAYS = 420  # enough for SMA200 + a year of signal context


def _history_sync(symbol: str):
    import yfinance as yf

    from tradingagents.dataflows.symbol_utils import normalize_symbol

    df = yf.Ticker(normalize_symbol(symbol)).history(period=f"{_HISTORY_DAYS}d")
    return df if not df.empty else None


async def _universe() -> list[str]:
    """Core US tickers (stocks + ETFs) — liquid names the rules were tested on."""
    async with session_factory()() as session:
        rows = await WatchlistRepository(session).list_all()
    return [
        t.symbol for t in rows
        if t.market == Market.US.value and t.category == "core" and t.tier != "paused"
    ]


async def _tactical_buy(symbol: str, rule: str) -> str | None:
    price = await live_price(symbol)
    equity = await paper_equity_usd("tactical")
    if price is None or equity is None:
        return None
    settings = get_settings()
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
    await ensure_cash("tactical", equity * settings.tactical_size_pct)

    async with session_factory()() as session, session.begin():
        repo = PortfolioRepository(session)
        account = await repo.get_account("tactical")
        if account is None:
            return None
        if await repo.get_position("tactical", symbol) is not None:
            return None
        alloc = min(equity * settings.tactical_size_pct, account.cash)
        if alloc < 50:
            logger.info("Tactical buy skipped for %s: insufficient cash", symbol)
            return None
        quantity = alloc / price
        account.cash -= alloc
        await repo.add_position(Position(
            account_type="tactical", symbol=symbol, market=Market.US.value,
            currency="USD", quantity=quantity, avg_price=price, stop_loss=stop,
            note=f"rule {rule}",
        ))
        await repo.add_trade(Trade(
            account_type="tactical", symbol=symbol, side="buy",
            quantity=quantity, price=price, currency="USD",
            reason=f"tactical {rule}",
        ))
    return f"bought {quantity:.4f} {symbol} @ {price:,.2f} (≈${alloc:,.0f})"


async def _in_cooldown(symbol: str, days: int) -> bool:
    """True when this symbol was sold from the tactical book within ``days``.

    Without this the rule re-buys whatever the stop just sold: in Jul 2026
    both AMZN and LLY were stopped out and re-entered within days at HIGHER
    prices, turning noise into realised losses on the round trip.
    """
    if days <= 0:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with session_factory()() as session:
        trades = await PortfolioRepository(session).list_trades(
            limit=500, account_type="tactical"
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


async def run_tactical() -> list[str]:
    """One end-of-day tactical pass. Returns human-readable action summaries."""
    settings = get_settings()
    rule = settings.tactical_rule.strip()
    if not rule:
        return []  # disabled — the backtest gate was not passed by default
    if rule not in RULES:
        logger.error("Unknown tactical rule %r; available: %s", rule, list(RULES))
        return []

    from app.services.notifier import Notifier

    universe = await _universe()
    async with session_factory()() as session:
        repo = PortfolioRepository(session)
        held = {p.symbol for p in await repo.list_positions("tactical")}

    # Daily-loss circuit breaker: compare live equity to today's snapshot.
    equity = await paper_equity_usd("tactical")
    block_entries = False
    if equity is not None:
        today = datetime.now(timezone.utc).date().isoformat()
        async with session_factory()() as session:
            snapshots = await PortfolioRepository(session).list_snapshots("tactical", limit=2)
        baseline = next(
            (s.equity_usd for s in snapshots if s.snapshot_date == today),
            snapshots[-1].equity_usd if snapshots else None,
        )
        if baseline and equity < baseline * (1 - settings.tactical_daily_loss_cap_pct / 100):
            block_entries = True
            logger.warning("Tactical circuit breaker: down >%s%% today — entries blocked",
                           settings.tactical_daily_loss_cap_pct)

    actions: list[str] = []
    for symbol in universe:
        df = await asyncio.to_thread(_history_sync, symbol)
        if df is None or len(df) < 260:
            continue
        try:
            signal = int(RULES[rule](df).iloc[-1])
        except Exception:
            logger.warning("Tactical signal failed for %s", symbol)
            continue

        if signal == 1 and symbol not in held:
            if block_entries or len(held) >= settings.tactical_max_positions:
                continue
            if await _in_cooldown(symbol, settings.tactical_reentry_cooldown_days):
                logger.info("Tactical entry for %s suppressed: re-entry cooldown", symbol)
                continue
            summary = await _tactical_buy(symbol, rule)
            if summary:
                held.add(symbol)
                actions.append(summary)
        elif signal == 0 and symbol in held:
            summary = await _paper_sell(
                symbol, "all", reason=f"tactical {rule} exit", book="tactical"
            )
            if summary:
                held.discard(symbol)
                actions.append(summary)

    if actions:
        notifier = Notifier(settings)
        await notifier.send_telegram(
            "⚡ <b>Tactical (" + rule + ")</b>\n" + "\n".join("· " + a for a in actions)
        )
    logger.info("Tactical pass done: %d action(s)", len(actions))
    return actions


async def record_equity_snapshots() -> None:
    """Daily equity per book — the scoreboard's raw data. Cheap, always on."""
    today = datetime.now(timezone.utc).date().isoformat()
    for book in ("strategic", "tactical"):
        equity = await paper_equity_usd(book)
        if equity is None:
            continue
        async with session_factory()() as session, session.begin():
            await PortfolioRepository(session).record_snapshot(book, today, equity)
    logger.info("Equity snapshots recorded for %s", today)
