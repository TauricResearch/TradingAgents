"""Deterministic quant features computed from OHLCV bars.

Inputs are contract bars; outputs are plain floats (or the MarketRegime
enum) that get packaged as MetricReadings for agent prompts and reused by
the Phase 4 pipeline and Phase 7 backtester.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from tradingagents.contracts import MarketRegime, OHLCVBar

# Annualization factors by bar count per year are the caller's concern;
# daily bars are the Phase 3 default.
TRADING_DAYS_PER_YEAR = 252


def _closes(bars: Sequence[OHLCVBar]) -> list[float]:
    if len(bars) < 3:
        raise ValueError(f"need at least 3 bars, got {len(bars)}")
    return [b.close for b in bars]


def realized_volatility(bars: Sequence[OHLCVBar], annualize: bool = True) -> float:
    """Stdev of log returns; annualized for daily bars by default."""
    closes = _closes(bars)
    log_returns = [math.log(b / a) for a, b in zip(closes, closes[1:], strict=False)]
    vol = statistics.stdev(log_returns)
    return vol * math.sqrt(TRADING_DAYS_PER_YEAR) if annualize else vol


def trend_slope(bars: Sequence[OHLCVBar]) -> tuple[float, float]:
    """OLS slope of closes vs bar index, normalized to %/bar, plus R².

    Returns (slope_pct_per_bar, r_squared). Slope is relative to the mean
    close so the number is comparable across price levels.
    """
    closes = _closes(bars)
    n = len(closes)
    xs = range(n)
    mean_x = (n - 1) / 2
    mean_y = math.fsum(closes) / n
    ss_xy = math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, closes, strict=False))
    ss_xx = math.fsum((x - mean_x) ** 2 for x in xs)
    ss_yy = math.fsum((y - mean_y) ** 2 for y in closes)
    slope = ss_xy / ss_xx
    r_squared = 0.0 if ss_yy == 0 else (ss_xy * ss_xy) / (ss_xx * ss_yy)
    return (slope / mean_y) * 100.0, r_squared


def close_zscore(bars: Sequence[OHLCVBar], window: int = 50) -> float:
    """Z-score of the latest close against the trailing window of closes."""
    closes = _closes(bars)
    if len(closes) < window:
        raise ValueError(f"need >= {window} bars for the z-score window, got {len(closes)}")
    tail = closes[-window:]
    mean = math.fsum(tail) / window
    stdev = statistics.stdev(tail)
    if stdev == 0:
        raise ValueError("zero-variance window has no defined z-score")
    return (closes[-1] - mean) / stdev


# Regime thresholds (daily bars). Deliberately coarse and documented:
# high/low volatility relative to a long-run 15% annualized anchor for
# metals; trend requires both slope magnitude and fit quality.
_HIGH_VOL = 0.30
_LOW_VOL = 0.10
_TREND_SLOPE_PCT = 0.08  # %/bar ~ 20% over 250 bars
_TREND_R2 = 0.55


def classify_regime(bars: Sequence[OHLCVBar]) -> MarketRegime:
    """Rule-based regime label from volatility and trend features."""
    vol = realized_volatility(bars)
    slope_pct, r_squared = trend_slope(bars)
    if vol >= _HIGH_VOL * 2:
        return MarketRegime.CRISIS
    if vol >= _HIGH_VOL:
        return MarketRegime.HIGH_VOLATILITY
    if abs(slope_pct) >= _TREND_SLOPE_PCT and r_squared >= _TREND_R2:
        return MarketRegime.TRENDING_UP if slope_pct > 0 else MarketRegime.TRENDING_DOWN
    if vol <= _LOW_VOL:
        return MarketRegime.LOW_VOLATILITY
    return MarketRegime.RANGING
