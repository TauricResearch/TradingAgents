"""Market-intelligence aggregation for the dashboard.

One endpoint pulls the free feeds the pipeline already trusts —
derivatives (funding/OI/mark), Fear & Greed, gold cross-asset
(DXY/US10Y/silver correlation), FRED macro, session — behind a shared TTL
cache. Each feed fails independently: an exception becomes an entry in
``missing_feeds`` (the MarketSnapshot disclosure convention) and the rest
still serve. The UI renders gaps honestly; it never fakes a reading.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from tradingagents.contracts import utc_now

logger = logging.getLogger(__name__)


def _reading_view(reading) -> dict:
    return {
        "name": reading.name,
        "value": reading.value,
        "unit": reading.unit,
        "as_of": reading.as_of.isoformat() if reading.as_of else None,
        "source": reading.source,
    }


class IntelService:
    def __init__(
        self,
        feeds: dict[str, Callable[[], list]] | None = None,
        calendar_source: Callable[[int], list[dict]] | None = None,
        ttl: float = 60.0,
        calendar_ttl: float = 6 * 3600.0,
        deadline: float = 10.0,
        now: Callable[[], float] = time.monotonic,
    ):
        self._feeds = feeds
        self._calendar_source = calendar_source
        self.ttl = ttl
        self.calendar_ttl = calendar_ttl
        self.deadline = deadline
        self._now = now
        self._lock = threading.Lock()
        self._pool = None  # lazy ThreadPoolExecutor, shared across snapshots
        self._cached: tuple[float, dict] | None = None
        self._cached_calendar: tuple[float, dict] | None = None

    # --- default wiring (built lazily so tests never construct real feeds) --------

    @property
    def feeds(self) -> dict[str, Callable[[], list]]:
        if self._feeds is None:
            from tradingagents.pro.ingestion.binance import (
                BinanceDerivativesFeed,
                BinanceSpotFeed,
            )
            from tradingagents.pro.ingestion.fred_macro import FredMacroFeed
            from tradingagents.pro.ingestion.gold_feeds import (
                GoldCrossAssetFeed,
                YFinanceDailyBarsFeed,
            )
            from tradingagents.pro.ingestion.onchain import (
                CoinMetricsFeed,
                FearGreedFeed,
            )

            derivatives = BinanceDerivativesFeed()
            spot = BinanceSpotFeed()
            self._feeds = {
                "binance_derivatives": derivatives.get_metrics,
                "orderbook_imbalance":
                    lambda: [spot.get_orderbook_imbalance("BTCUSDT")],
                "fear_greed": FearGreedFeed().get_metrics,
                "coinmetrics": CoinMetricsFeed().get_metrics,
                "gold_cross_asset":
                    GoldCrossAssetFeed(YFinanceDailyBarsFeed()).get_metrics,
                "fred_macro": FredMacroFeed().get_metrics,
            }
        return self._feeds

    def _calendar_fetch(self, days: int) -> list[dict]:
        if self._calendar_source is not None:
            return self._calendar_source(days)
        from tradingagents.pro.ingestion.fred_macro import FredMacroFeed

        return FredMacroFeed().get_release_dates(days_ahead=days)

    # --- views ---------------------------------------------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            if self._cached and self._now() - self._cached[0] < self.ttl:
                return self._cached[1]

        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

        from tradingagents.pro.ingestion.sessions import current_session

        # feeds fetch in parallel under a hard deadline: one blackholed
        # vendor (blocked egress hangs, not errors) must never make the
        # whole intelligence view take minutes — it becomes a missing_feeds
        # line instead
        metrics: list[dict] = []
        missing: list[str] = []
        feeds = dict(self.feeds)
        # persistent pool: a `with` block would join hanging threads on
        # exit, re-introducing the very stall the deadline exists to stop.
        # A blackholed fetch keeps its worker busy until the transport
        # timeout; the TTL cache bounds how often that can pile up.
        with self._lock:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(max_workers=8,
                                                thread_name_prefix="intel")
            pool = self._pool
        futures = {name: pool.submit(fetch) for name, fetch in feeds.items()}
        started = time.monotonic()
        for feed_name, future in futures.items():
            remaining = max(0.05, self.deadline - (time.monotonic() - started))
            try:
                readings = future.result(timeout=remaining)
                metrics.extend(_reading_view(r) for r in readings)
            except FutureTimeout:
                future.cancel()
                missing.append(f"{feed_name}: no response within "
                               f"{self.deadline:.0f}s (vendor unreachable?)")
            except Exception as exc:
                missing.append(f"{feed_name}: {exc}")
        view = {
            "as_of": utc_now().isoformat(),
            "session": current_session(utc_now()).value,
            "metrics": metrics,
            "missing_feeds": missing,
            # honest map of what money hasn't bought yet (UX: trust signal)
            "unsubscribed_feeds": [
                {"name": "liquidations", "provider": "Coinglass"},
                {"name": "whale_flows", "provider": "Glassnode"},
                {"name": "etf_flows", "provider": "Farside/SoSoValue"},
                {"name": "gold_microstructure", "provider": "Databento/Polygon"},
            ],
        }
        with self._lock:
            self._cached = (self._now(), view)
        return view

    def calendar(self, days: int = 30) -> dict:
        days = max(1, min(days, 90))
        with self._lock:
            if (self._cached_calendar
                    and self._now() - self._cached_calendar[0] < self.calendar_ttl):
                return self._cached_calendar[1]
        releases: list[dict] = []
        missing: list[str] = []
        try:
            releases = self._calendar_fetch(days)
        except Exception as exc:
            missing.append(f"fred_calendar: {exc}")
        view = {"releases": releases, "missing_feeds": missing,
                "as_of": utc_now().isoformat()}
        with self._lock:
            self._cached_calendar = (self._now(), view)
        return view
