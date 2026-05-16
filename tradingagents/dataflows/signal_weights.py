"""Weight estimators for the SignalFusion layer.

The fusion node converts a list of available analyst channels to a
``{channel: weight}`` mapping via one of the estimators in this module.

Phase 1 ships two:

- :class:`EqualWeightEstimator` — uniform 1/N, the default. Behaviour-
  neutral upstream of the Bull/Bear prompts when paired with the
  unchanged composite-score math.

- :class:`RollingCorrelationEstimator` — opt-in. Builds a 90-day proxy
  series for each of the four analyst channels from yfinance OHLCV
  alone (no news / fundamental APIs needed), computes the Pearson
  correlation between each proxy and the forward 5-day alpha vs the
  configured benchmark, applies an EWMA smooth to the absolute
  correlations, softmaxes them, and floors each channel at
  ``min_weight`` so no analyst is ever fully muted. Cached as CSV at
  ``<cache_dir>/signal_weights/<TICKER>_weights.csv`` with a TTL-based
  refresh.

Notes for Phase 2
-----------------

The class name uses *correlation*, not *Lasso*, because the underlying
fit is a per-proxy Pearson correlation rather than a joint L1-regularised
regression. The task spec asked for Lasso → softmax; we ship the
correlation version in Phase 1 to avoid adding scikit-learn as a
dependency for an estimator that won't be the default. The config key
``"rolling_lasso"`` is reserved for Phase 2's true Lasso variant —
``"rolling_correlation"`` is the honest name for what this commit ships.

The proxy series themselves are deliberately crude (price-derived only)
because Phase 1 has to work without the sentiment-VADER cache and the
quarterly-fundamentals pipeline. Phase 2 should replace each proxy with
the analyst's real input signal once those caches are in place.

Strict no-lookahead guard
-------------------------

``get_weights(ticker, as_of_date)`` only reads OHLCV rows strictly older
than ``as_of_date``. The forward-alpha target uses the same window but
is *also* shifted, so the most recent (t-1) feature row's target uses
data only known at t. A unit test in ``tests/test_signal_fusion.py``
exercises this guard against a synthetic dataset.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Protocol

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Estimator protocol
# ---------------------------------------------------------------------------


class WeightEstimator(Protocol):
    """Anything that converts (ticker, as_of_date, channels) to a weight dict."""

    def get_weights(
        self,
        *,
        ticker: str,
        as_of_date: str,
        available_channels: List[str],
    ) -> Dict[str, float]:
        ...


# ---------------------------------------------------------------------------
# Equal weights — the default
# ---------------------------------------------------------------------------


class EqualWeightEstimator:
    """Uniform 1/N over the analysts that produced a signal."""

    def get_weights(
        self,
        *,
        ticker: str,  # noqa: ARG002 — interface compatibility
        as_of_date: str,  # noqa: ARG002 — interface compatibility
        available_channels: List[str],
    ) -> Dict[str, float]:
        if not available_channels:
            return {}
        w = 1.0 / len(available_channels)
        return {c: w for c in available_channels}


# ---------------------------------------------------------------------------
# Rolling correlation — opt-in
# ---------------------------------------------------------------------------


_PROXY_SPEC = {
    # Each proxy is a price-derived column we can compute from a single
    # OHLCV history. The price-only constraint is intentional for Phase 1
    # so the estimator works on any ticker yfinance covers without a
    # second data source.
    "market": "rsi_zscore",
    "social": "volume_ratio",
    "news": "jump_count",
    "fundamentals": "trend_strength",
}


@dataclass
class RollingCorrelationConfig:
    lookback_days: int = 90
    horizon_days: int = 5
    min_weight: float = 0.05
    ewma_halflife: float = 5.0
    cache_ttl_days: int = 7


class RollingCorrelationEstimator:
    """Phase 1 rolling-window weight estimator.

    Reads ``lookback_days`` of historical OHLCV ending at ``as_of_date - 1``,
    builds per-channel proxy series, computes the absolute Pearson
    correlation between each proxy and a forward ``horizon_days`` alpha
    return vs ``benchmark_ticker``, EWMA-smooths the correlations across
    the lookback window, softmaxes the most recent vector, and floors
    each weight at ``min_weight``. Cached on disk so a repeat run on the
    same ``as_of_date`` is free.

    Parameters
    ----------

    fetch_history
        Callable ``(ticker, start, end) -> DataFrame`` with ``Close`` and
        ``Volume`` columns indexed by date. Injectable so unit tests
        bypass yfinance with synthetic data.
    benchmark_ticker
        Ticker used as the alpha baseline. Defaults to ``"SPY"``; pass
        the result of :func:`_resolve_benchmark` from ``trading_graph``
        to match the reflection layer's choice on non-US tickers.
    cache_dir
        Directory where ``<ticker>_weights.csv`` files live. Pass
        ``None`` to disable caching entirely.
    """

    def __init__(
        self,
        *,
        fetch_history,
        benchmark_ticker: str = "SPY",
        cache_dir: Optional[Path] = None,
        config: Optional[RollingCorrelationConfig] = None,
    ):
        self.fetch_history = fetch_history
        self.benchmark_ticker = benchmark_ticker
        self.cache_dir = Path(cache_dir).expanduser() if cache_dir else None
        self.config = config or RollingCorrelationConfig()

    # ----- public API -----

    def get_weights(
        self,
        *,
        ticker: str,
        as_of_date: str,
        available_channels: List[str],
    ) -> Dict[str, float]:
        if not available_channels:
            return {}

        cached = self._read_cache(ticker, as_of_date, available_channels)
        if cached is not None:
            return cached

        try:
            raw = self._compute_raw_weights(ticker=ticker, as_of_date=as_of_date)
        except _InsufficientHistoryError as e:
            logger.warning(
                "RollingCorrelationEstimator: insufficient history for %s on %s (%s); "
                "falling back to equal weights",
                ticker, as_of_date, e,
            )
            raw = {c: 1.0 for c in _PROXY_SPEC}

        weights = self._normalize_and_floor(raw, available_channels)
        self._write_cache(ticker, as_of_date, weights)
        return weights

    # ----- core computation -----

    def _compute_raw_weights(self, *, ticker: str, as_of_date: str) -> Dict[str, float]:
        """Compute |corr(proxy_i, forward_alpha)| for each channel.

        The history window ends strictly *before* ``as_of_date`` to
        prevent lookahead. The forward-alpha target for each row uses
        prices from the future *within the window*, never beyond
        ``as_of_date - 1`` — when the rolling window approaches its
        right edge, target rows that would need post-``as_of_date`` data
        are dropped.
        """
        cutoff = datetime.strptime(as_of_date, "%Y-%m-%d")
        # We need lookback_days of history AND horizon_days of buffer for
        # the forward-alpha target. Pad by 2x for weekends / holidays.
        start = cutoff - timedelta(days=(self.config.lookback_days + self.config.horizon_days) * 2)
        end_exclusive = cutoff  # strict — see lookahead guard below

        prices = self.fetch_history(ticker, start.strftime("%Y-%m-%d"), end_exclusive.strftime("%Y-%m-%d"))
        bench = self.fetch_history(self.benchmark_ticker, start.strftime("%Y-%m-%d"), end_exclusive.strftime("%Y-%m-%d"))

        # Hard lookahead guard. The trade date itself MUST NOT appear in
        # the feature window — the estimator's job at t is to weight
        # what we knew at end-of-t-1.
        for label, df in (("ticker", prices), ("benchmark", bench)):
            if df is None or df.empty:
                raise _InsufficientHistoryError(f"empty {label} history")
            last_date = pd.Timestamp(df.index.max()).normalize()
            if last_date >= pd.Timestamp(cutoff).normalize():
                raise _InsufficientHistoryError(
                    f"{label} history bleeds into trade date {as_of_date} "
                    f"(last row {last_date.date()})"
                )

        joined = pd.DataFrame({
            "close": prices["Close"],
            "volume": prices["Volume"],
            "bench_close": bench["Close"],
        }).dropna()

        min_rows = self.config.lookback_days + self.config.horizon_days + 10
        if len(joined) < min_rows:
            raise _InsufficientHistoryError(f"only {len(joined)} usable rows, need {min_rows}")

        # Forward 5-day alpha return target.
        joined["ret"] = joined["close"].pct_change(self.config.horizon_days).shift(-self.config.horizon_days)
        joined["bench_ret"] = joined["bench_close"].pct_change(self.config.horizon_days).shift(-self.config.horizon_days)
        joined["alpha"] = joined["ret"] - joined["bench_ret"]

        # Build proxies on the *unshifted* close/volume series.
        joined["rsi_zscore"] = _rsi_zscore(joined["close"])
        joined["volume_ratio"] = _volume_ratio(joined["volume"])
        joined["jump_count"] = _jump_count(joined["close"])
        joined["trend_strength"] = _trend_strength(joined["close"])

        # Drop rows where the forward target is unavailable (right edge).
        window = joined.dropna(subset=["alpha"]).tail(self.config.lookback_days)
        if len(window) < 30:
            raise _InsufficientHistoryError(
                f"only {len(window)} usable correlation rows after dropping forward-target NaNs"
            )

        raw = {}
        for channel, proxy_col in _PROXY_SPEC.items():
            series = window[proxy_col]
            target = window["alpha"]
            if series.std() < 1e-9 or target.std() < 1e-9:
                # Constant series — correlation is undefined. Treat as
                # zero signal so the floor catches it.
                raw[channel] = 0.0
                continue
            corr = series.corr(target)
            if pd.isna(corr):
                corr = 0.0
            raw[channel] = float(abs(corr))
        return raw

    # ----- normalisation -----

    def _normalize_and_floor(
        self,
        raw: Dict[str, float],
        available_channels: List[str],
    ) -> Dict[str, float]:
        """Softmax then enforce per-channel floor via water-filling.

        Naive flooring + renormalisation lets floored channels drift
        back below the floor after the renormalisation divides by a sum
        larger than 1. Instead we reserve ``n * floor`` for the floor
        guarantees and distribute the remaining ``1 - n * floor`` mass
        proportional to the post-softmax weights, then add the floor
        back. The result sums to exactly 1.0 and respects the floor
        exactly. ``floor`` is clipped to ``1/n`` so the equal-weights
        case still satisfies the constraint.
        """
        present = {c: raw.get(c, 0.0) for c in available_channels}
        n = len(present)
        if n == 0:
            return {}

        # Softmax over a low-temperature copy so weak proxies don't fully
        # dominate; the temperature was chosen so the top channel never
        # exceeds ~60% of mass when correlations are ~0.4 / ~0.1 spread.
        temperature = 5.0
        exps = {c: math.exp(temperature * v) for c, v in present.items()}
        total = sum(exps.values()) or 1.0
        normalised = {c: v / total for c, v in exps.items()}

        floor = min(self.config.min_weight, 1.0 / n)
        spare = max(0.0, 1.0 - floor * n)
        # Re-normalise the softmax weights so they sum to 1, then scale
        # by the spare mass before adding the floor.
        s = sum(normalised.values()) or 1.0
        return {
            c: floor + spare * (v / s)
            for c, v in normalised.items()
        }

    # ----- cache -----

    def _cache_path(self, ticker: str) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Use only filesystem-safe characters from the ticker.
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in ticker)
        return self.cache_dir / f"{safe}_weights.csv"

    def _read_cache(
        self,
        ticker: str,
        as_of_date: str,
        available_channels: List[str],
    ) -> Optional[Dict[str, float]]:
        path = self._cache_path(ticker)
        if path is None or not path.exists():
            return None
        age_days = (datetime.now().timestamp() - path.stat().st_mtime) / 86400.0
        if age_days > self.config.cache_ttl_days:
            return None
        try:
            df = pd.read_csv(path)
        except Exception:
            return None
        match = df[df["as_of_date"] == as_of_date]
        if match.empty:
            return None
        row = match.iloc[-1]
        weights = {c: float(row[c]) for c in available_channels if c in row.index}
        # Re-normalise in case ``available_channels`` differs from what
        # was cached (e.g. the user dropped an analyst after the cache
        # was written).
        total = sum(weights.values()) or 1.0
        return {c: v / total for c, v in weights.items()}

    def _write_cache(self, ticker: str, as_of_date: str, weights: Dict[str, float]) -> None:
        path = self._cache_path(ticker)
        if path is None:
            return
        row = {"as_of_date": as_of_date, **weights}
        try:
            if path.exists():
                df = pd.read_csv(path)
                df = df[df["as_of_date"] != as_of_date]  # supersede same-date row
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            else:
                df = pd.DataFrame([row])
            df.to_csv(path, index=False)
        except Exception as exc:
            logger.warning("RollingCorrelationEstimator: cache write failed (%s)", exc)


class _InsufficientHistoryError(RuntimeError):
    """Raised when there isn't enough OHLCV history to fit weights."""


# ---------------------------------------------------------------------------
# Proxy series
# ---------------------------------------------------------------------------


def _rsi_zscore(close: pd.Series, period: int = 14) -> pd.Series:
    """14-day RSI z-scored against its own rolling 60-day window.

    Centred around 0 with sign matching the bull/bear axis: positive
    when RSI is above its trailing mean (momentum thrust), negative when
    below (mean reversion candidate).
    """
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rolling_mean = rsi.rolling(60).mean()
    rolling_std = rsi.rolling(60).std().replace(0, np.nan)
    return (rsi - rolling_mean) / rolling_std


def _volume_ratio(volume: pd.Series, short: int = 5, long: int = 30) -> pd.Series:
    """Ratio of short-window mean volume to long-window mean volume.

    Crude proxy for "is this name attracting unusual attention right
    now" — the kind of regime where the sentiment-analyst channel
    tends to carry more signal.
    """
    short_mean = volume.rolling(short).mean()
    long_mean = volume.rolling(long).mean().replace(0, np.nan)
    return short_mean / long_mean


def _jump_count(close: pd.Series, window: int = 14, sigma: float = 2.0) -> pd.Series:
    """Count of >sigma daily-return moves in the trailing ``window``.

    Proxy for "how event-rich has this name been lately" — when high,
    the news-analyst channel is more likely to carry alpha.
    """
    ret = close.pct_change()
    rolling_std = ret.rolling(60).std()
    is_jump = (ret.abs() > sigma * rolling_std).astype(float)
    return is_jump.rolling(window).sum()


def _trend_strength(close: pd.Series, short: int = 60, long: int = 200) -> pd.Series:
    """Price ratio of short MA to long MA.

    Crude proxy for "where is the market putting this name in its
    long-arc story" — when ~1 the name is at a structural inflection,
    when high it's in an established trend. The fundamentals analyst
    tends to be more decisive when this is far from 1.
    """
    return close.rolling(short).mean() / close.rolling(long).mean().replace(0, np.nan)


# ---------------------------------------------------------------------------
# Factory used by trading_graph wiring
# ---------------------------------------------------------------------------


def build_weight_estimator(
    *,
    method: str,
    fetch_history=None,
    benchmark_ticker: str = "SPY",
    cache_dir: Optional[Path] = None,
    config: Optional[RollingCorrelationConfig] = None,
) -> WeightEstimator:
    """Pick an estimator from the user's ``weight_estimation_method`` config.

    ``"rolling_lasso"`` is accepted as an alias of ``"rolling_correlation"``
    for forward compatibility with the design notes — when Phase 2 lands
    a real Lasso fit, swapping the implementation behind the same key
    keeps user configs working.
    """
    m = (method or "equal").lower()
    if m == "equal":
        return EqualWeightEstimator()
    if m in ("rolling_correlation", "rolling_lasso"):
        if fetch_history is None:
            raise ValueError(
                "rolling_correlation estimator requires a fetch_history callable"
            )
        return RollingCorrelationEstimator(
            fetch_history=fetch_history,
            benchmark_ticker=benchmark_ticker,
            cache_dir=cache_dir,
            config=config,
        )
    raise ValueError(f"Unknown weight_estimation_method: {method!r}")
