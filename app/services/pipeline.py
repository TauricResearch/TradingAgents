"""Orchestrates analysis runs: slot-based scheduled windows and manual triggers.

A run analyzes a batch of watchlist tickers sequentially, persists each
outcome, applies watchlist rotation, alerts on rating changes, and sends one
digest email per batch.

DB sessions are short-lived: one to snapshot the batch, then one per ticker to
persist its outcome. A batch takes minutes-to-hours of LLM time, and holding a
single transaction across it would just invite lock trouble for zero benefit.

Quota guard: ``assistant_daily_run_budget`` caps ticker-runs per UTC day
across all slots and manual triggers, so a misconfigured schedule cannot burn
a limited LLM quota (e.g. Ollama cloud free tier) in one day.
"""

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

import pytz

from app.core.config import get_settings
from app.core.logging import run_id_var
from app.domain import Market, Tier
from app.models.base import session_factory
from app.models.entities import SignalRecord
from app.repositories.portfolio import PortfolioRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.signals import SignalRepository
from app.repositories.watchlist import WatchlistRepository
from app.services.broker_rules import parse_review_days
from app.services.notifier import Notifier
from app.services.paper_broker import execute_signal, live_price, usd_rate
from app.services.rotation import next_rotation_state
from app.services.runner import run_analysis_sync

logger = logging.getLogger(__name__)

MARKET_TZ = {
    Market.US: pytz.timezone("America/New_York"),
    Market.INDIA: pytz.timezone("Asia/Kolkata"),
    Market.CRYPTO: pytz.utc,
}

# Serializes batches so a manual trigger can't overlap a scheduled one
# (duplicate spend, provider rate limits). Scheduler jobs also set
# max_instances=1.
_run_lock = asyncio.Lock()

# What the deep-analysis engine is chewing on right now (None = idle).
# Surfaced via /health so the dashboard can show scheduled runs, not just
# manual clicks.
current_analysis: dict | None = None

# When several reviews are due at once, spend the budget in order of how
# actionable the ticker's last verdict was: open positions are handled by a
# higher queue tier already; below that, Buy/Overweight-rated tickers first
# (closest to action), then Hold (could flip), then Underweight, then Sell
# (already rejected), never-analyzed last within their tier.
_RATING_PRIORITY = {"Buy": 0, "Overweight": 1, "Hold": 2, "Underweight": 3, "Sell": 4}


def review_priority(last_rating: str | None) -> int:
    return _RATING_PRIORITY.get(last_rating, 5)


@dataclass(frozen=True)
class TickerItem:
    symbol: str
    asset_type: str
    prev_rating: str | None
    market: Market
    category: str = "satellite"


def _utc_midnight() -> datetime:
    now = datetime.now(pytz.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _utc_week_start() -> datetime:
    midnight = _utc_midnight()
    return midnight - timedelta(days=midnight.weekday())


async def runs_remaining_today() -> int:
    """Runs still allowed by BOTH the daily and the weekly budget."""
    settings = get_settings()
    async with session_factory()() as session:
        signals = SignalRepository(session)
        used_today = await signals.count_since(_utc_midnight())
        used_week = await signals.count_since(_utc_week_start())
    return max(0, min(
        settings.assistant_daily_run_budget - used_today,
        settings.assistant_weekly_run_budget - used_week,
    ))


async def weekly_budget_used_fraction() -> float:
    settings = get_settings()
    async with session_factory()() as session:
        used_week = await SignalRepository(session).count_since(_utc_week_start())
    return used_week / max(1, settings.assistant_weekly_run_budget)


async def run_slot(slot_id: int) -> list[dict]:
    """Execute one scheduled slot.

    A slot is a window of opportunity, not an obligation: it funds, in
    priority order, (1) position reviews that are due or event-triggered,
    (2) screener initiations, (3) due reviews without positions, (4) event
    movers, and (5) — only while most of the weekly budget remains — a
    heartbeat run for the stalest ticker. A quiet day analyzes nothing and
    costs nothing.
    """
    async with session_factory()() as session:
        slot = await ScheduleRepository(session).get(slot_id)
    if slot is None or not slot.enabled:
        logger.info("Slot %s missing or disabled; skipping", slot_id)
        return []

    remaining = await runs_remaining_today()
    if remaining <= 0:
        logger.warning("Run budget exhausted; skipping slot %r", slot.label)
        return []
    batch_size = min(slot.max_tickers, remaining)

    market = Market(slot.market) if slot.market else None
    queue = await _select_candidates(market, batch_size)
    if not queue:
        logger.info("Slot %r: nothing due, no events — 0 runs", slot.label)
        return []

    items = [
        TickerItem(t.symbol, t.asset_type, t.last_rating, Market(t.market),
                   t.category or "satellite")
        for t in queue
    ]
    return await _run_batch(slot.label, items)


async def _select_candidates(market: Market | None, batch_size: int) -> list:
    """Priority-ordered ticker selection for a slot."""
    from app.repositories.portfolio import PortfolioRepository as _PRepo

    now = datetime.now(pytz.utc).replace(tzinfo=None)  # DB datetimes come back naive-UTC

    async with session_factory()() as session:
        repo = WatchlistRepository(session)
        rows = [
            t for t in await repo.list_all()
            if t.tier != Tier.PAUSED.value
            and (market is None or t.market == market.value)
        ]
        held = {p.symbol for p in await _PRepo(session).list_positions("paper")}

    def _naive(dt):
        return dt.replace(tzinfo=None) if dt is not None and dt.tzinfo else dt

    due = [t for t in rows if _naive(t.next_review_at) is not None
           and _naive(t.next_review_at) <= now]
    never_run = [t for t in rows if t.last_run_at is None]

    def _staleness(t):
        return _naive(t.last_run_at) or datetime.min

    p1_position_due = sorted(
        (t for t in due if t.symbol in held), key=_staleness
    )
    p2_initiations = [t for t in never_run if t.added_by == "screener"]
    p3_reviews = sorted(
        (t for t in due if t.symbol not in held),
        key=lambda t: (review_priority(t.last_rating), _staleness(t)),
    )

    picked: list = []
    seen: set[str] = set()

    def take(candidates):
        for t in candidates:
            if len(picked) >= batch_size:
                return
            if t.symbol not in seen:
                seen.add(t.symbol)
                picked.append(t)

    take(p1_position_due)
    take(p2_initiations)
    take(p3_reviews)

    # P4: event movers — volatility-scaled, only checked if room remains and
    # only for tickers not already picked (price checks are free but slow-ish).
    if len(picked) < batch_size:
        candidates = [t for t in rows if t.symbol not in seen and t.last_run_at is not None]
        movers = await _event_movers(candidates)
        take(movers)

    # P5: heartbeat — backfill the slot with the STALEST tickers so the budget
    # is actually spent. Previously this took exactly one ticker and switched
    # off at 70% weekly usage, both written when Ollama's weekly cap made every
    # run precious. That scarcity is gone, and the binding constraint on the
    # experiment is now the opposite problem: too few observations. August's
    # verdict was unprovable at an effective sample size of 3.19, so an idle
    # slot is a wasted day, not a saving.
    #
    # A reserve is still kept so a burst of heartbeats cannot starve the
    # position reviews and screener initiations that arrive later in the week.
    if len(picked) < batch_size and await weekly_budget_used_fraction() < 0.9:
        stalest = sorted(
            (t for t in rows if t.symbol not in seen),
            key=lambda t: (_naive(t.last_run_at) or datetime.min),
        )
        take(stalest)

    return picked


def _price_move_since_sync(symbol: str, since) -> float | None:
    """Percent price change since a past datetime (free yfinance check)."""
    import yfinance as yf

    from tradingagents.dataflows.symbol_utils import normalize_symbol

    try:
        history = yf.Ticker(normalize_symbol(symbol)).history(
            start=since.date().isoformat()
        )
        closes = history["Close"].dropna() if not history.empty else None
        if closes is None or len(closes) < 2:
            return None
        first, last = float(closes.iloc[0]), float(closes.iloc[-1])
        # NaN fails every threshold comparison silently, so an unpriced ticker
        # would simply never register as a mover.
        if not (math.isfinite(first) and math.isfinite(last)) or first <= 0:
            return None
        return (last - first) / first * 100
    except Exception:
        logger.warning("Price-move check failed for %s", symbol)
        return None


async def _event_movers(tickers: list) -> list:
    """Tickers whose price moved past their own volatility-scaled threshold."""
    from app.services.volatility import daily_volatility_pct_sync, event_threshold_pct

    movers = []
    for ticker in tickers[:15]:  # cap the free-API volume per slot
        move = await asyncio.to_thread(
            _price_move_since_sync, ticker.symbol, ticker.last_run_at
        )
        if move is None:
            continue
        vol = await asyncio.to_thread(daily_volatility_pct_sync, ticker.symbol)
        threshold = event_threshold_pct(vol)
        if abs(move) >= threshold:
            logger.info(
                "Event trigger: %s moved %+.1f%% since last analysis (threshold %.1f%%)",
                ticker.symbol, move, threshold,
            )
            movers.append(ticker)
    return movers


async def run_ticker(symbol: str) -> list[dict]:
    """Manual single-ticker analysis (dashboard "Analyze now"). Budget applies."""
    if await runs_remaining_today() <= 0:
        logger.warning("Run budget exhausted; refusing manual run for %s", symbol)
        return []
    async with session_factory()() as session:
        ticker = await WatchlistRepository(session).get_by_symbol(symbol)
    if ticker is None:
        logger.warning("Manual run requested for %s but it is not on the watchlist", symbol)
        return []
    item = TickerItem(ticker.symbol, ticker.asset_type, ticker.last_rating,
                      Market(ticker.market), ticker.category or "satellite")
    return await _run_batch(f"manual {ticker.symbol}", [item])


async def run_market(market: Market, include_weekly: bool = True) -> list[dict]:
    """Manual full-market run (dashboard / API trigger). Budget still applies."""
    remaining = await runs_remaining_today()
    if remaining <= 0:
        logger.warning("Run budget exhausted; refusing manual %s run", market.value)
        return []
    async with session_factory()() as session:
        due = await WatchlistRepository(session).get_due_for_run(
            market, include_weekly, limit=remaining
        )
        items = [
            TickerItem(t.symbol, t.asset_type, t.last_rating, Market(t.market),
                       t.category or "satellite")
            for t in due
        ]
    return await _run_batch(f"manual {market.value}", items)


async def _run_batch(label: str, items: list[TickerItem]) -> list[dict]:
    settings = get_settings()
    notifier = Notifier(settings)

    async with _run_lock:
        run_id_var.set(f"{label.replace(' ', '-')}-{uuid4().hex[:8]}")
        logger.info("Batch started: %r, %d ticker(s)", label, len(items))

        global current_analysis
        digest_rows: list[dict] = []
        batch_date = ""
        for item in items:
            trade_date = datetime.now(MARKET_TZ[item.market]).date().isoformat()
            batch_date = batch_date or trade_date
            current_analysis = {
                "symbol": item.symbol,
                "label": label,
                "started_at": datetime.now(pytz.utc).isoformat(),
            }
            try:
                outcome = await asyncio.to_thread(
                    run_analysis_sync, item.symbol, trade_date, item.asset_type, settings
                )
            finally:
                current_analysis = None
            row = await _persist_outcome(item.market, item.symbol, item.prev_rating, outcome)
            digest_rows.append(row)

            if not outcome.ok:
                await notifier.alert_run_error(item.symbol, trade_date, outcome.error or "")
            elif row["changed"]:
                await notifier.alert_rating_change(
                    symbol=item.symbol,
                    market=item.market,
                    trade_date=trade_date,
                    prev_rating=item.prev_rating,
                    rating=outcome.rating or "?",
                    decision_text=outcome.decision_text,
                    holding_note=await _real_holding_context(item.symbol),
                )

            # Mirror the signal into the paper book (mechanical, live prices).
            if outcome.ok and outcome.rating:
                try:
                    summary = await execute_signal(
                        item.symbol, item.market, outcome.rating,
                        outcome.decision_text, item.category,
                    )
                except Exception:
                    logger.exception("Paper execution failed for %s", item.symbol)
                    summary = None
                if summary:
                    await notifier.send_telegram(f"📄 <b>Paper trade</b>: {summary}")

        if digest_rows:
            await notifier.send_digest(label, batch_date, digest_rows)
        logger.info("Batch finished: %r", label)
        return digest_rows


async def _real_holding_context(symbol: str) -> str | None:
    """P&L context for the user's real position in this symbol, if any."""
    async with session_factory()() as session:
        position = await PortfolioRepository(session).get_position("real", symbol)
    if position is None:
        return None
    price = await live_price(symbol)
    rate = await usd_rate(position.currency)
    since = position.opened_at.date().isoformat() if position.opened_at else "?"
    qty = f"{position.quantity:.4f}".rstrip("0").rstrip(".")
    if price is None or rate is None:
        return f"You hold {qty} since {since} @ {position.avg_price:,.2f}"
    pct = (price - position.avg_price) / position.avg_price * 100
    return (
        f"You hold {qty} @ {position.avg_price:,.2f} since {since} "
        f"({pct:+.1f}% at today's {price:,.2f})"
    )


async def _persist_outcome(market, symbol, prev_rating, outcome) -> dict:
    """Store the signal record and apply watchlist rotation in one short transaction."""
    changed = outcome.ok and outcome.rating != prev_rating
    async with session_factory()() as session, session.begin():
        signals = SignalRepository(session)
        await signals.add(SignalRecord(
            symbol=symbol,
            market=market.value,
            trade_date=outcome.trade_date,
            rating=outcome.rating,
            prev_rating=prev_rating,
            changed=changed,
            status="success" if outcome.ok else "error",
            error=outcome.error,
            report_path=outcome.report_path,
            duration_seconds=outcome.duration_seconds,
        ))

        watchlist = WatchlistRepository(session)
        ticker = await watchlist.get_by_symbol(symbol)
        if ticker is not None:
            now = datetime.now(pytz.utc)
            ticker.last_run_at = now
            if outcome.ok and outcome.rating:
                held = await PortfolioRepository(session).get_position("paper", symbol)
                if (
                    ticker.added_by == "screener"
                    and outcome.rating == "Hold"
                    and held is None
                ):
                    # Fast-demote: one Hold on a screener pick with no position
                    # is verdict enough — don't spend 5 runs learning it's dull.
                    ticker.tier = Tier.WEEKLY.value
                    ticker.consecutive_holds += 1
                    logger.info("Fast-demote: screener pick %s -> weekly after Hold", symbol)
                else:
                    new_tier, holds = next_rotation_state(
                        Tier(ticker.tier),
                        ticker.consecutive_holds,
                        outcome.rating,
                        demote_after=get_settings().assistant_demote_after_holds,
                    )
                    if new_tier.value != ticker.tier:
                        logger.info(
                            "Rotation: %s %s -> %s after rating %s",
                            symbol, ticker.tier, new_tier.value, outcome.rating,
                        )
                    ticker.tier = new_tier.value
                    ticker.consecutive_holds = holds
                ticker.last_rating = outcome.rating
                # The analysis names its own next check-up date (clamped 3-21d),
                # then earnings pull it forward: never review AFTER a report
                # that lands first.
                review_days = parse_review_days(outcome.decision_text)
                review_at = (now + timedelta(days=review_days)).replace(tzinfo=None)
                try:
                    from app.services.earnings import (
                        clamp_review_to_earnings,
                        fetch_earnings_context_sync,
                    )

                    context = await asyncio.to_thread(fetch_earnings_context_sync, symbol)
                    if context is not None:
                        clamped = clamp_review_to_earnings(
                            review_at, now.replace(tzinfo=None), context.next_earnings_date
                        )
                        if clamped != review_at:
                            logger.info(
                                "Review for %s pulled forward to %s (earnings %s)",
                                symbol, clamped.date(), context.next_earnings_date,
                            )
                        review_at = clamped
                except Exception:
                    logger.warning("Earnings clamp failed for %s", symbol)
                ticker.next_review_at = review_at

    return {
        "symbol": symbol,
        "prev_rating": prev_rating,
        "rating": outcome.rating,
        "changed": changed,
        "status": "success" if outcome.ok else "error",
        "error": outcome.error,
        "report_path": outcome.report_path,
    }
