"""Quote tick pollers → SSE `tick` events.

Backend polling turns any QuoteFeed (Delta Exchange, OANDA) into the
live tick stream the frontend already renders per symbol. Vendor-
friendly by construction: zero requests while nobody is subscribed to
the stream, exponential backoff on rate limits.
"""

from __future__ import annotations

import logging
import threading

from tradingagents.dataflows.errors import VendorRateLimitError
from tradingagents.pro.dashboard.events import EventBroadcaster

logger = logging.getLogger(__name__)


class QuoteTickPoller:
    def __init__(
        self,
        feed,                       # any QuoteFeed (Delta, OANDA, ...)
        broadcaster: EventBroadcaster,
        symbol: str = "XAU_USD",
        display_symbol: str = "XAUUSD",
        interval: float = 5.0,
        backoff_cap: float = 60.0,
    ):
        self.feed = feed
        self.broadcaster = broadcaster
        self.symbol = symbol
        self.display_symbol = display_symbol
        self.interval = interval
        self.backoff_cap = backoff_cap
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name=f"tick-poller-{self.display_symbol}", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def poll_once(self) -> bool:
        """One cycle; returns True when a tick was published (tests call
        this directly — the thread loop is just pacing around it)."""
        if self.broadcaster.subscriber_count == 0:
            return False  # nobody listening: no vendor calls
        quote = self.feed.get_quote(self.symbol)
        self.broadcaster.publish("tick", {
            "symbol": self.display_symbol,
            "bid": quote.bid,
            "ask": quote.ask,
            "last": quote.last,
            "ts": quote.ts.isoformat(),
        })
        return True

    def _run(self) -> None:
        delay = self.interval
        while not self._stop.wait(delay):
            try:
                self.poll_once()
                delay = self.interval
            except VendorRateLimitError:
                delay = min(max(delay * 2, self.interval), self.backoff_cap)
                logger.warning("%s quote feed throttled; backing off to %.0fs",
                               self.display_symbol, delay)
            except Exception:
                logger.exception("%s tick poll failed; continuing", self.display_symbol)
                delay = self.interval


# backwards-compatible alias (pre-Delta name)
GoldTickPoller = QuoteTickPoller
