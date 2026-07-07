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


def compute_indicators(
    bars: Sequence[OHLCVBar], names: Sequence[str] = DEFAULT_INDICATOR_NAMES
) -> list[IndicatorReading]:
    """Compute the latest value of each named indicator from bars.

    All bars must share one timeframe (an indicator over mixed-timeframe
    bars is meaningless). Indicators whose warm-up window exceeds the data
    (NaN at the tail) are skipped rather than reported as garbage; the
    caller sees the omission and can record the gap.
    """
    unknown = sorted(set(names) - set(INDICATOR_SPECS))
    if unknown:
        raise ValueError(f"unknown indicators {unknown}; supported: {sorted(INDICATOR_SPECS)}")
    timeframes = {b.timeframe for b in bars}
    if len(timeframes) != 1:
        raise ValueError(f"bars span multiple timeframes: {sorted(t.value for t in timeframes)}")
    timeframe = timeframes.pop()

    frame = wrap(bars_to_dataframe(bars))
    readings: list[IndicatorReading] = []
    for name in names:
        min_bars, params, outputs = INDICATOR_SPECS[name]
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
