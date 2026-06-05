"""Pure technical-indicator math over OHLCV bars.

A "bar" is a dict with at least ``high``, ``low``, ``close`` (chronological
order, oldest first). Functions return ``None`` when there is not enough data
rather than raising, so callers can degrade gracefully.
"""

from __future__ import annotations

from typing import Any, Optional


def _closes(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["close"]) for b in bars]


def sma(values: list[float], period: int) -> Optional[float]:
    """Simple moving average of the last ``period`` values."""
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values: list[float], period: int) -> Optional[float]:
    """Exponential moving average (seeded with the first SMA)."""
    if period <= 0 or len(values) < period:
        return None
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    e = seed
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def true_ranges(bars: list[dict[str, Any]]) -> list[float]:
    """True Range series; needs the previous close, so length is len(bars)-1."""
    out: list[float] = []
    for prev, cur in zip(bars, bars[1:]):
        high, low, prev_close = float(cur["high"]), float(cur["low"]), float(prev["close"])
        out.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return out


def atr(bars: list[dict[str, Any]], period: int = 14) -> Optional[float]:
    """Average True Range (simple average of the last ``period`` true ranges)."""
    trs = true_ranges(bars)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Relative Strength Index over ``period`` (simple average of gains/losses)."""
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for prev, cur in zip(closes[-period - 1:], closes[-period:]):
        change = cur - prev
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def max_drawdown(closes: list[float]) -> float:
    """Largest peak-to-trough decline, as a positive fraction (0..1)."""
    if not closes:
        return 0.0
    peak = closes[0]
    mdd = 0.0
    for c in closes:
        peak = max(peak, c)
        if peak > 0:
            mdd = max(mdd, (peak - c) / peak)
    return mdd


def high_low_52w(bars: list[dict[str, Any]], window: int = 252) -> dict[str, Any]:
    """52-week-style high/low band and where the last close sits in it."""
    sample = bars[-window:]
    if not sample:
        return {"high": None, "low": None, "range_position": None}
    high = max(float(b["high"]) for b in sample)
    low = min(float(b["low"]) for b in sample)
    last = float(sample[-1]["close"])
    band = high - low
    pos = (last - low) / band if band else 0.5
    return {"high": high, "low": low, "range_position": pos}


_DISPATCH = {"atr", "rsi", "sma", "ema", "max_drawdown", "range_52w"}


def compute_indicator(name: str, bars: list[dict[str, Any]], **params: Any) -> Any:
    """Single parametric entry point (the family-B tool surface)."""
    name = name.lower()
    if name == "atr":
        return atr(bars, params.get("period", 14))
    if name == "rsi":
        return rsi(_closes(bars), params.get("period", 14))
    if name == "sma":
        return sma(_closes(bars), params.get("period", 50))
    if name == "ema":
        return ema(_closes(bars), params.get("period", 50))
    if name == "max_drawdown":
        return max_drawdown(_closes(bars))
    if name == "range_52w":
        return high_low_52w(bars, params.get("window", 252))
    raise ValueError(f"unknown indicator '{name}' (known: {sorted(_DISPATCH)})")
