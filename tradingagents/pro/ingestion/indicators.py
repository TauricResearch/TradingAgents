"""Deterministic indicator engine: OHLCV bars -> IndicatorReading contracts.

Uses the stockstats library already depended on by the base framework, so
Pro indicator values match what the existing market analyst tooling would
report for the same bars. LLM agents receive these readings inside a
MarketSnapshot; they never compute indicators themselves (Constraint 2).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from stockstats import wrap

from tradingagents.contracts import IndicatorReading, OHLCVBar
from tradingagents.pro.ingestion.derived import bars_to_dataframe

# Contract name -> (min_bars, params, {output key -> stockstats column}).
# Multi-line indicators (MACD, Bollinger) group their lines into one
# reading so agents see them as a unit. min_bars is the warm-up window:
# stockstats silently computes partial means below it (min_periods=1),
# which would hand agents a misleading number, so we skip instead.
INDICATOR_SPECS: dict[str, tuple[int, dict, dict[str, str]]] = {
    "RSI_14": (15, {"period": 14}, {"value": "rsi_14"}),
    "EMA_10": (10, {"period": 10}, {"value": "close_10_ema"}),
    "SMA_50": (50, {"period": 50}, {"value": "close_50_sma"}),
    "SMA_200": (200, {"period": 200}, {"value": "close_200_sma"}),
    "MACD": (
        35,  # slow EMA (26) + signal (9)
        {"fast": 12, "slow": 26, "signal": 9},
        {"macd": "macd", "signal": "macds", "histogram": "macdh"},
    ),
    "BOLL": (
        20,
        {"period": 20, "std": 2},
        {"middle": "boll", "upper": "boll_ub", "lower": "boll_lb"},
    ),
    "ATR_14": (15, {"period": 14}, {"value": "atr_14"}),
}

DEFAULT_INDICATOR_NAMES = tuple(INDICATOR_SPECS)

# Parameterized families (trader review G7): EMA_21, RSI_9, ... resolve to
# stockstats columns at request time. Fixed-period entries above stay valid
# (and keep their curated warm-up windows).
_PARAM_FAMILIES: dict[str, str] = {
    "EMA": "close_{n}_ema",
    "SMA": "close_{n}_sma",
    "RSI": "rsi_{n}",
    "ATR": "atr_{n}",
}
_PARAM_RE = __import__("re").compile(r"^(EMA|SMA|RSI|ATR)_(\d{1,3})$")
MIN_PERIOD, MAX_PERIOD = 2, 400

# Anchored intraday VWAP: cumulative sum(typical*vol)/sum(vol) reset each
# UTC day. Only meaningful within a session — daily/weekly bars get a 422.
VWAP_NAME = "VWAP"
_INTRADAY = {"1m", "5m", "15m", "30m", "1h", "4h"}


def _spec_for(name: str) -> tuple[int, dict, dict[str, str]] | None:
    """Resolve a fixed or parameterized indicator name; None = unknown."""
    if name in INDICATOR_SPECS:
        return INDICATOR_SPECS[name]
    match = _PARAM_RE.match(name)
    if not match:
        return None
    family, period = match.group(1), int(match.group(2))
    if not MIN_PERIOD <= period <= MAX_PERIOD:
        raise ValueError(
            f"{name}: period must be {MIN_PERIOD}-{MAX_PERIOD}")
    warmup = period + 1 if family in ("RSI", "ATR") else period
    return (warmup, {"period": period},
            {"value": _PARAM_FAMILIES[family].format(n=period)})


def _vwap_series(bars: Sequence[OHLCVBar]) -> list[float | None]:
    values: list[float | None] = []
    day = None
    pv_sum = 0.0
    vol_sum = 0.0
    for bar in bars:
        bar_day = bar.start.date()
        if bar_day != day:
            day, pv_sum, vol_sum = bar_day, 0.0, 0.0
        typical = (bar.high + bar.low + bar.close) / 3.0
        volume = bar.volume or 0.0
        pv_sum += typical * volume
        vol_sum += volume
        values.append(pv_sum / vol_sum if vol_sum > 0 else None)
    return values


def _validate(bars: Sequence[OHLCVBar], names: Sequence[str]) -> None:
    for name in names:
        if name == VWAP_NAME:
            if bars and bars[0].timeframe.value not in _INTRADAY:
                raise ValueError(
                    "VWAP is session-anchored and needs an intraday "
                    "timeframe (1m-4h); daily/weekly bars have no session")
            continue
        if _spec_for(name) is None:
            raise ValueError(
                f"unknown indicator {name!r}; supported: fixed "
                f"{sorted(INDICATOR_SPECS)}, parameterized EMA_n/SMA_n/"
                f"RSI_n/ATR_n (n {MIN_PERIOD}-{MAX_PERIOD}), and VWAP "
                f"(intraday)")
    timeframes = {b.timeframe for b in bars}
    if len(timeframes) != 1:
        raise ValueError(f"bars span multiple timeframes: {sorted(t.value for t in timeframes)}")


def compute_indicator_series(
    bars: Sequence[OHLCVBar], names: Sequence[str] = DEFAULT_INDICATOR_NAMES
) -> dict[str, dict]:
    """Full per-bar series of each named indicator (for charting).

    Same deterministic engine and warm-up discipline as compute_indicators
    (Constraint 2: the UI renders these numbers, it never computes them).
    Positions inside the warm-up window — where stockstats would emit a
    partial mean — come back as None, as do NaN/inf values.
    """
    _validate(bars, names)
    frame = wrap(bars_to_dataframe(bars))
    result: dict[str, dict] = {}
    for name in names:
        if name == VWAP_NAME:
            result[name] = {"params": {"anchor": "utc_day"},
                            "series": {"value": _vwap_series(bars)}}
            continue
        min_bars, params, outputs = _spec_for(name)
        series: dict[str, list[float | None]] = {}
        for key, column in outputs.items():
            values: list[float | None] = []
            for i, raw in enumerate(frame[column].tolist()):
                value = float(raw)
                if i + 1 < min_bars or math.isnan(value) or math.isinf(value):
                    values.append(None)
                else:
                    values.append(value)
            series[key] = values
        result[name] = {"params": params, "series": series}
    return result


def compute_indicators(
    bars: Sequence[OHLCVBar], names: Sequence[str] = DEFAULT_INDICATOR_NAMES
) -> list[IndicatorReading]:
    """Compute the latest value of each named indicator from bars.

    All bars must share one timeframe (an indicator over mixed-timeframe
    bars is meaningless). Indicators whose warm-up window exceeds the data
    (NaN at the tail) are skipped rather than reported as garbage; the
    caller sees the omission and can record the gap.
    """
    _validate(bars, names)  # guarantees non-empty, single-timeframe bars
    timeframe = bars[0].timeframe

    frame = wrap(bars_to_dataframe(bars))
    readings: list[IndicatorReading] = []
    for name in names:
        if name == VWAP_NAME:
            last = _vwap_series(bars)[-1]
            if last is not None:
                readings.append(IndicatorReading(
                    name=name, timeframe=timeframe,
                    value={"value": last}, params={"anchor": "utc_day"}))
            continue
        min_bars, params, outputs = _spec_for(name)
        if len(bars) < min_bars:
            continue
        values: dict[str, float] = {}
        for key, column in outputs.items():
            raw = float(frame[column].iloc[-1])
            if math.isnan(raw) or math.isinf(raw):
                values = {}
                break
            values[key] = raw
        if values:
            readings.append(
                IndicatorReading(name=name, timeframe=timeframe, value=values, params=params)
            )
    return readings
