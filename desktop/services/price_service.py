"""Per-ticker yfinance price fetcher with TTL cache.

Fetches one ticker at a time so a single invalid symbol never poisons
the results for others.  A 5-minute TTL cache avoids hammering yfinance
on repeated page loads, and stale data is returned (with ``is_stale=True``)
when a refresh fails so the UI can display a warning badge rather than
nothing at all.

Thread-safe: the alert engine may call from a background thread while the
NiceGUI UI calls from the main thread.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defensive yfinance import
# ---------------------------------------------------------------------------

try:
    import yfinance as yf  # type: ignore[import-untyped]

    _YF_AVAILABLE: Final[bool] = True
except ImportError:
    yf = None  # type: ignore[assignment]
    _YF_AVAILABLE = False
    logger.warning(
        "yfinance is not installed — PriceService will return error results. "
        "Install with: pip install yfinance"
    )


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceResult:
    """Immutable snapshot of a single ticker's price data."""

    ticker: str
    price: float | None
    previous_close: float | None
    change_pct: float | None
    is_stale: bool
    fetched_at: str | None
    error: str | None


@dataclass(frozen=True)
class _CachedPrice:
    """Internal cache entry — never exposed to callers."""

    result: PriceResult
    fetched_at_dt: datetime


@dataclass(frozen=True)
class _CachedHistorical:
    """Internal cache entry for historical OHLCV data."""

    data: list[dict]
    fetched_at_dt: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_TTL: Final[int] = 300  # 5 minutes
_HISTORICAL_TTL: Final[int] = 3600  # 1 hour
_MAX_WORKERS: Final[int] = 5


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso_now() -> str:
    return _now().isoformat()


def _compute_change_pct(
    price: float | None, previous_close: float | None
) -> float | None:
    if price is None or previous_close is None or previous_close == 0.0:
        return None
    return round(((price - previous_close) / previous_close) * 100, 4)


def _unavailable_result(ticker: str, error: str) -> PriceResult:
    """Build a PriceResult for when yfinance is missing or a fetch fails."""
    return PriceResult(
        ticker=ticker,
        price=None,
        previous_close=None,
        change_pct=None,
        is_stale=False,
        fetched_at=None,
        error=error,
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PriceService:
    """Thread-safe, TTL-cached, per-ticker price fetcher.

    Parameters
    ----------
    ttl_seconds:
        How many seconds a cached price is considered fresh (default 300).
    """

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL) -> None:
        self._ttl_seconds: Final[int] = ttl_seconds
        self._cache: dict[str, _CachedPrice] = {}
        self._historical_cache: dict[str, _CachedHistorical] = {}
        self._lock = threading.Lock()
        self._historical_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_price(self, ticker: str) -> PriceResult:
        """Fetch the current price for *ticker*.

        Returns a cached value when within the TTL window.  If the live
        fetch fails but a previous value exists, returns it with
        ``is_stale=True``.
        """
        ticker = ticker.upper().strip()

        if not _YF_AVAILABLE:
            return _unavailable_result(ticker, "yfinance is not installed")

        with self._lock:
            cached = self._cache.get(ticker)
            if cached is not None:
                age = (_now() - cached.fetched_at_dt).total_seconds()
                if age < self._ttl_seconds:
                    return cached.result

        # Outside the lock: network I/O can be slow.
        result = self._fetch_single(ticker, stale_fallback=cached)

        with self._lock:
            if result.error is None:
                self._cache[ticker] = _CachedPrice(
                    result=result, fetched_at_dt=_now()
                )

        return result

    def get_prices(self, tickers: list[str]) -> dict[str, PriceResult]:
        """Fetch prices for multiple tickers with per-ticker isolation.

        Uses a thread pool (up to 5 workers) so the total wall-clock time
        is dominated by the single slowest fetch, not the sum.
        """
        if not tickers:
            return {}

        results: dict[str, PriceResult] = {}

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(self.get_price, t): t for t in tickers
            }
            for future in as_completed(futures):
                t = futures[future]
                try:
                    results[t.upper().strip()] = future.result()
                except Exception:
                    # Should never happen — get_price catches internally.
                    logger.exception("Unexpected error fetching %s", t)
                    results[t.upper().strip()] = _unavailable_result(
                        t.upper().strip(), "unexpected executor error"
                    )

        return results

    def invalidate(self, ticker: str | None = None) -> None:
        """Clear the price cache for *ticker*, or all tickers if ``None``."""
        with self._lock:
            if ticker is None:
                self._cache.clear()
            else:
                self._cache.pop(ticker.upper().strip(), None)

        with self._historical_lock:
            if ticker is None:
                self._historical_cache.clear()
            else:
                self._historical_cache.pop(ticker.upper().strip(), None)

    def get_historical(
        self, ticker: str, period: str = "3mo"
    ) -> list[dict] | None:
        """Return historical OHLCV rows for *ticker*.

        Cached separately with a 1-hour TTL.  Returns ``None`` on error.
        """
        ticker = ticker.upper().strip()

        if not _YF_AVAILABLE:
            logger.warning("yfinance unavailable — cannot fetch history for %s", ticker)
            return None

        cache_key = f"{ticker}:{period}"

        with self._historical_lock:
            cached = self._historical_cache.get(cache_key)
            if cached is not None:
                age = (_now() - cached.fetched_at_dt).total_seconds()
                if age < _HISTORICAL_TTL:
                    return cached.data

        data = self._fetch_historical(ticker, period)

        if data is not None:
            with self._historical_lock:
                self._historical_cache[cache_key] = _CachedHistorical(
                    data=data, fetched_at_dt=_now()
                )

        return data

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_single(
        self,
        ticker: str,
        *,
        stale_fallback: _CachedPrice | None,
    ) -> PriceResult:
        """Hit yfinance for a single ticker.

        On failure, return the stale fallback (if available) with
        ``is_stale=True``, or an error result.
        """
        try:
            info = yf.Ticker(ticker).fast_info
            price: float | None = getattr(info, "last_price", None)
            previous_close: float | None = getattr(
                info, "previous_close", None
            )

            if price is None:
                raise ValueError(f"No price data returned for {ticker}")

            return PriceResult(
                ticker=ticker,
                price=round(price, 4),
                previous_close=(
                    round(previous_close, 4) if previous_close is not None else None
                ),
                change_pct=_compute_change_pct(price, previous_close),
                is_stale=False,
                fetched_at=_iso_now(),
                error=None,
            )

        except Exception as exc:
            logger.error("Failed to fetch price for %s: %s", ticker, exc)

            if stale_fallback is not None:
                stale = stale_fallback.result
                return PriceResult(
                    ticker=stale.ticker,
                    price=stale.price,
                    previous_close=stale.previous_close,
                    change_pct=stale.change_pct,
                    is_stale=True,
                    fetched_at=stale.fetched_at,
                    error=str(exc),
                )

            return _unavailable_result(ticker, str(exc))

    @staticmethod
    def _fetch_historical(ticker: str, period: str) -> list[dict] | None:
        """Download historical OHLCV data and return as a list of dicts."""
        try:
            df = yf.Ticker(ticker).history(period=period)

            if df is None or df.empty:
                logger.warning("No historical data for %s (period=%s)", ticker, period)
                return None

            rows: list[dict] = []
            for date, row in df.iterrows():
                rows.append(
                    {
                        "date": str(date.date()) if hasattr(date, "date") else str(date),
                        "open": round(float(row["Open"]), 4),
                        "high": round(float(row["High"]), 4),
                        "low": round(float(row["Low"]), 4),
                        "close": round(float(row["Close"]), 4),
                        "volume": int(row["Volume"]),
                    }
                )

            return rows

        except Exception as exc:
            logger.error(
                "Failed to fetch historical data for %s (period=%s): %s",
                ticker,
                period,
                exc,
            )
            return None
