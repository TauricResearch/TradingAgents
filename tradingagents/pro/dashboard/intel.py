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
import re
import threading
import time
from collections.abc import Callable

from tradingagents.contracts import utc_now

logger = logging.getLogger(__name__)

CORRELATION_SYMBOLS = ("BTC-USD", "XAUUSD", "DXY", "SILVER", "US10Y")


def _friendly_error(exc: Exception) -> str:
    """One short human line for the UI; the raw exception goes to logs.

    Vendor exceptions embed full request URLs and repr noise (the review
    caught a raw '403 Client Error: Forbidden for url: https://...' on the
    Intel page) — the dashboard shows the kind of failure, never the
    plumbing."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        hints = {401: "auth rejected", 403: "forbidden — subscription or rate limit?",
                 404: "endpoint missing", 429: "rate limited"}
        hint = hints.get(status, "server error" if status >= 500 else "request rejected")
        return f"HTTP {status} ({hint})"
    name = type(exc).__name__
    if "Timeout" in name:
        return "timed out"
    if "Connection" in name:
        return "unreachable"
    # deliberate, short messages ("FRED_API_KEY not set") stay — minus any
    # embedded URLs; anything long is vendor plumbing and shows its kind
    text = re.sub(r"https?://\S+", "", str(exc)).strip(" ;:,-")
    if text and len(text) <= 80:
        return text
    return name


def correlation_matrix(marketdata, symbols, window: int = 30,
                       deadline: float = 10.0) -> dict:
    """Pairwise Pearson correlations of daily log returns (deterministic
    math on close prices — the UI renders, never computes). Calendars are
    aligned on shared dates (BTC trades weekends, gold doesn't); symbols
    without enough overlapping data are disclosed, never zero-filled.
    Bars fetch in parallel under a deadline — one blackholed vendor must
    not make the matrix take minutes."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

    import numpy as np
    import pandas as pd

    from tradingagents.contracts import Timeframe

    closes: dict[str, pd.Series] = {}
    missing: list[str] = []
    pool = ThreadPoolExecutor(max_workers=len(symbols) or 1,
                              thread_name_prefix="corr")
    futures = {
        symbol: pool.submit(
            marketdata.get_bars, symbol, Timeframe.D1, window + 10
        )
        for symbol in symbols
    }
    started = time.monotonic()
    for symbol, future in futures.items():
        remaining = max(0.05, deadline - (time.monotonic() - started))
        try:
            bars = future.result(timeout=remaining)
            closes[symbol] = pd.Series(
                [b.close for b in bars],
                index=[b.start.date() for b in bars],
            )
        except FutureTimeout:
            future.cancel()
            missing.append(f"{symbol}: no response within {deadline:.0f}s")
        except Exception as exc:
            logger.warning("correlation bars for %s failed", symbol, exc_info=True)
            missing.append(f"{symbol}: {_friendly_error(exc)}")
    pool.shutdown(wait=False)  # never join a blackholed fetch

    matrix: dict[str, dict[str, float]] = {}
    used_days = 0
    if len(closes) >= 2:
        frame = pd.DataFrame(closes).sort_index().dropna()
        returns = np.log(frame / frame.shift(1)).dropna().tail(window)
        used_days = len(returns)
        if used_days >= 5:
            corr = returns.corr()
            matrix = {
                a: {b: round(float(corr.loc[a, b]), 3) for b in corr.columns}
                for a in corr.index
            }
        else:
            missing.append(
                f"only {used_days} overlapping daily returns; need >= 5"
            )
    return {
        "window": window,
        "used_days": used_days,
        "symbols": [s for s in symbols if s in matrix],
        "matrix": matrix,
        "missing": missing,
        "as_of": utc_now().isoformat(),
    }


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
        self._cached_correlations: dict[tuple, tuple[float, dict]] = {}

    # --- default wiring (built lazily so tests never construct real feeds) --------

    @property
    def feeds(self) -> dict[str, Callable[[], list]]:
        if self._feeds is None:
            from tradingagents.pro.dashboard.prefs import default_data_dir
            from tradingagents.pro.ingestion.binance import (
                BinanceDerivativesFeed,
                BinanceSpotFeed,
            )
            from tradingagents.pro.ingestion.delta_exchange import (
                DeltaExchangeFeed,
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
            from tradingagents.pro.ingestion.positioning import (
                GoldCotFeed,
                GoldVolFeed,
            )

            derivatives = BinanceDerivativesFeed()
            spot = BinanceSpotFeed()
            delta = DeltaExchangeFeed()
            yf_daily = YFinanceDailyBarsFeed()
            self._feeds = {
                "delta_derivatives": lambda: delta.get_metrics("BTCUSD"),
                "binance_derivatives": derivatives.get_metrics,
                "orderbook_imbalance":
                    lambda: [spot.get_orderbook_imbalance("BTCUSDT")],
                "fear_greed": FearGreedFeed().get_metrics,
                "coinmetrics": CoinMetricsFeed().get_metrics,
                "gold_cross_asset":
                    GoldCrossAssetFeed(yf_daily).get_metrics,
                "fred_macro": FredMacroFeed().get_metrics,
                "gold_cot": GoldCotFeed(
                    cache_path=default_data_dir() / "cot_cache.json"
                ).get_metrics,
                "gold_vol": GoldVolFeed(yf_daily).get_metrics,
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
                logger.warning("intel feed %s failed", feed_name, exc_info=True)
                missing.append(f"{feed_name}: {_friendly_error(exc)}")
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

    def correlations(self, marketdata, window: int = 30,
                     symbols: tuple[str, ...] = CORRELATION_SYMBOLS) -> dict:
        window = max(5, min(window, 250))
        cache_key = (window, symbols)
        with self._lock:
            cached = self._cached_correlations.get(cache_key)
            if cached and self._now() - cached[0] < 3600.0:
                return cached[1]
        view = correlation_matrix(marketdata, symbols, window)
        with self._lock:
            self._cached_correlations[cache_key] = (self._now(), view)
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
            from tradingagents.pro.ingestion.econ_calendar import (
                enrich_calendar,
                next_major_event,
            )

            releases = enrich_calendar(self._calendar_fetch(days))
            upcoming = next_major_event(releases, utc_now())
        except Exception as exc:
            logger.warning("calendar fetch failed", exc_info=True)
            missing.append(f"fred_calendar: {_friendly_error(exc)}")
            upcoming = None
        view = {"releases": releases, "missing_feeds": missing,
                "next_major": upcoming,
                "as_of": utc_now().isoformat()}
        with self._lock:
            self._cached_calendar = (self._now(), view)
        return view
