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
    tickers = list(state.tickers())
    if not tickers:
        return
    try:
        df = yf.download(tickers=tickers, period="1d", interval="1m", progress=False, group_by="ticker")
    except Exception:
        log.exception("yfinance total failure; skipping poll")
        return

    for ticker in tickers:
        snap = state.snapshots.get(ticker) or PriceSnapshot()
        try:
            # With ``group_by="ticker"`` yfinance returns a MultiIndex where
            # the OUTER level is the field (Close/Open/...) and the INNER
            # level is the ticker — even for a single-ticker list. So
            # ``df[ticker]["Close"]`` works for both single and multi.
            series = df[ticker]["Close"]
            if hasattr(series, "empty") and series.empty:
                snap.stale = True
            else:
                values = list(series.dropna().tail(30))
                if not values:
                    snap.stale = True
                else:
                    snap.price = float(values[-1])
                    snap.sparkline = [float(v) for v in values]
                    snap.stale = False
            # change_pct is the percent move from the previous trading
            # session's close. fast_info is a lightweight single-field
            # lookup; the CLI uses it for the same purpose elsewhere.
            # Guard against zero to avoid div-by-zero on newly-listed
            # tickers and on stale prices.
            prev_close = float(
                yf.Ticker(ticker).fast_info.get("previousClose", 0) or 0
            )
            if prev_close > 0 and snap.price > 0 and not snap.stale:
                snap.change_pct = (snap.price - prev_close) / prev_close * 100.0
            else:
                snap.change_pct = 0.0
        except Exception:
            log.exception("price lookup failed for %s; marking stale", ticker)
            snap.stale = True
            snap.change_pct = 0.0
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


class PriceFeed:
    def __init__(self, state: PriceState, poll_s: int = 15):
        self.state = state
        self.poll_s = poll_s
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def _loop(self, broadcast: Optional[Callable[[dict], None]]) -> None:
        while not self._stop.is_set():
            try:
                await _poll_once(self.state, broadcast)
            except Exception:
                log.exception("poll loop iteration crashed; continuing")
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
