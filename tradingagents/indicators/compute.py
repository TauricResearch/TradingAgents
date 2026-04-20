"""Fetch indicator values using the existing stockstats pipeline.

Loads OHLCV data once and computes all indicators on a single
StockDataFrame instance — no redundant disk I/O.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# stockstats indicator names to fetch, grouped by interpretation key.
_STATS = [
    "rsi_14", "macd", "macds", "macdh",
    "boll_ub", "boll_lb", "boll",
    "close_50_sma", "close_200_sma",
]


def fetch_indicators(symbol: str, curr_date: str) -> dict[str, dict[str, Any]]:
    """Fetch indicator values via stockstats for *symbol* as of *curr_date*.

    Loads data once and computes all indicators in a single pass.
    Returns a dict keyed by indicator group name. Missing indicators omitted.
    """
    try:
        from tradingagents.dataflows.stockstats_utils import load_ohlcv
        from stockstats import wrap
    except ImportError:
        logger.warning("indicators: stockstats or dataflows not available")
        return {}

    try:
        df = load_ohlcv(symbol, curr_date)
    except Exception as exc:
        logger.warning("indicators: load_ohlcv failed for %s: %s", symbol, exc)
        return {}

    if df.empty or len(df) < 2:
        return {}

    try:
        ss = wrap(df)
        # Trigger computation of all indicators in one pass
        for stat in _STATS:
            _ = ss[stat]
    except Exception as exc:
        logger.warning("indicators: stockstats computation failed for %s: %s", symbol, exc)
        return {}

    # Extract last row values
    import pandas as pd
    curr_date_str = pd.to_datetime(curr_date).strftime("%Y-%m-%d")
    ss["date_str"] = ss["date"].dt.strftime("%Y-%m-%d") if "date" in ss.columns else ""
    row = ss[ss["date_str"] == curr_date_str]
    if row.empty:
        row = ss.iloc[[-1]]  # fallback to last available row

    def _val(col: str) -> float | None:
        try:
            v = float(row[col].iloc[0])
            return None if pd.isna(v) else v
        except (KeyError, IndexError):
            return None

    results: dict[str, dict[str, Any]] = {}

    # RSI
    rsi = _val("rsi_14")
    if rsi is not None:
        results["rsi"] = {"value": rsi, "period": 14}

    # MACD
    macd_val = _val("macd")
    if macd_val is not None:
        results["macd"] = {
            "value": macd_val,
            "signal": _val("macds"),
            "histogram": _val("macdh"),
        }

    # Bollinger
    upper = _val("boll_ub")
    lower = _val("boll_lb")
    if upper is not None and lower is not None:
        results["bollinger"] = {
            "value": _val("boll"),
            "upper": upper,
            "lower": lower,
        }

    # SMA crossover
    sma50 = _val("close_50_sma")
    sma200 = _val("close_200_sma")
    if sma50 is not None and sma200 is not None:
        # Detect crossover from recent data
        crossover = None
        try:
            diff = ss["close_50_sma"] - ss["close_200_sma"]
            recent = diff.iloc[-5:]
            signs = recent.dropna().apply(lambda x: 1 if x > 0 else -1)
            if len(signs) >= 2 and signs.iloc[-1] != signs.iloc[0]:
                crossover = "golden_cross" if signs.iloc[-1] > 0 else "death_cross"
        except Exception:
            pass
        results["sma_crossover"] = {
            "sma50": sma50,
            "sma200": sma200,
            "crossover": crossover,
        }

    return results
