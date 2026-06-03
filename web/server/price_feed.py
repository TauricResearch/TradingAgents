"""Background poller that fans out live prices to all WS clients."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

import yfinance as yf

from web.server import events


log = logging.getLogger(__name__)


@dataclass
class PriceSnapshot:
    price: float = 0.0
    prev_close: float = 0.0
    change_pct: float = 0.0
    sparkline: list[float] = field(default_factory=list)
    stale: bool = False


@dataclass
class PriceState:
    snapshots: dict[str, PriceSnapshot]
    tickers: Callable[[], list[str]]


async def _poll_once(state: PriceState, broadcast: Optional[Callable[[dict], None]]) -> None:
    """Fast poll: fetch current price via yfinance fast_info for every ticker.

    This runs every ``poll_s`` seconds (default 2s) and uses the lightweight
    ``fast_info`` API which returns the last-trade price.  Sparkline/history
    data is fetched separately by ``_update_sparklines`` every ~60s.
    """
    tickers = list(state.tickers())
    if not tickers:
        return

    for ticker in tickers:
        snap = state.snapshots.get(ticker) or PriceSnapshot()
        try:
            info = yf.Ticker(ticker).fast_info

            # Real-time last-trade price.  fast_info.get() accepts both
            # camelCase and snake_case keys.
            price = info.get("lastPrice") or info.get("last_price")

            if price is not None and float(price) > 0:
                snap.price = float(price)

                # Previous close — fetch once and cache in the snapshot so
                # subsequent polls avoid an extra API round-trip.
                #
                # yfinance fast_info exposes TWO previous-close values:
                #   - ``regularMarketPreviousClose``: the prior REGULAR
                #     session's close, the standard reference used by every
                #     financial site ("today's change" vs yesterday's close)
                #   - ``previousClose``: an intraday/adjusted value that
                #     can differ by 0.5-1% on real tickers (e.g. NVDA,
                #     TSLA, MSFT) and yields a visibly wrong change_pct
                #
                # Prefer the regular-session value; fall back to
                # ``previousClose`` for tickers/sessions that don't
                # populate it.
                if snap.prev_close <= 0:
                    prev_close = (
                        info.get("regularMarketPreviousClose")
                        or info.get("previousClose")
                        or info.get("previous_close")
                    )
                    if prev_close is not None:
                        snap.prev_close = float(prev_close)

                if snap.prev_close > 0:
                    snap.change_pct = (snap.price - snap.prev_close) / snap.prev_close * 100.0
                else:
                    snap.change_pct = 0.0
                snap.stale = False
            else:
                snap.stale = True
        except Exception:
            log.exception("fast_info failed for %s; marking stale", ticker)
            snap.stale = True

        state.snapshots[ticker] = snap

        if broadcast is not None:
            broadcast(events.make_event(
                "price_update",
                run_id=0,
                data={
                    "ticker": ticker,
                    "price": snap.price,
                    "change_pct": snap.change_pct,
                    "sparkline": snap.sparkline,
                    "stale": snap.stale,
                },
            ))


# ── sparkline refresh (heavy, runs every ~60s) ──────────────────────────

async def _update_sparklines(state: PriceState) -> None:
    """Download 1m-bar history for all watchlist tickers and update snapshots.

    This is intentionally kept separate from ``_poll_once`` because
    ``yf.download(interval="1m")`` is a heavy multi-ticker request; we
    only run it every ~60 seconds.
    """
    tickers = list(state.tickers())
    if not tickers:
        return

    try:
        df = yf.download(tickers=tickers, period="1d", interval="1m", progress=False, group_by="ticker")
    except Exception:
        log.exception("sparkline yfinance download failed")
        return

    for ticker in tickers:
        snap = state.snapshots.get(ticker)
        if snap is None:
            continue
        try:
            series = df[ticker]["Close"]
            if hasattr(series, "empty") and not series.empty:
                values = list(series.dropna().tail(30))
                snap.sparkline = [float(v) for v in values]
        except Exception:
            pass


# ── poll loop ───────────────────────────────────────────────────────────

class PriceFeed:
    def __init__(self, state: PriceState, poll_s: int = 2):
        self.state = state
        self.poll_s = poll_s
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def _loop(self, broadcast: Optional[Callable[[dict], None]]) -> None:
        sparkline_counter = 0
        # Run sparkline refresh on the very first iteration too so new
        # tickers don't sit with an empty sparkline for a full minute.
        while not self._stop.is_set():
            try:
                await _poll_once(self.state, broadcast)
            except Exception:
                log.exception("poll loop iteration crashed; continuing")

            sparkline_counter += 1
            # Refresh sparklines every ~30 iterations (~60s at 2s poll),
            # and also on the very first iteration.
            if sparkline_counter >= 30 or sparkline_counter == 1:
                sparkline_counter = 0
                try:
                    await _update_sparklines(self.state)
                except Exception:
                    log.exception("sparkline update crashed; continuing")

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_s)
            except asyncio.TimeoutError:
                pass

    def start(self, broadcast: Optional[Callable[[dict], None]] = None) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(broadcast))

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
