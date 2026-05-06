"""Technical indicators computed in pure pandas/numpy.

Replaces the old ``stockstats`` dependency. The selection mirrors the
indicators the Market Analyst prompt mentions (SMA / EMA / MACD / RSI /
Bollinger / ATR / VWMA) so the analyst can keep referring to them by
the same names.
"""

from __future__ import annotations

from typing import Iterable, List, Dict

import pandas as pd


_SUPPORTED = {
    "close_50_sma",
    "close_200_sma",
    "close_10_ema",
    "macd",
    "macds",
    "macdh",
    "rsi",
    "boll",
    "boll_ub",
    "boll_lb",
    "atr",
    "vwma",
}


def candles_to_df(candles: Iterable[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(list(candles))
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    return df


def supported() -> List[str]:
    return sorted(_SUPPORTED)


def compute(df: pd.DataFrame, indicator: str) -> pd.Series:
    """Compute a single indicator series aligned to ``df.index``."""
    name = indicator.strip().lower()
    if name not in _SUPPORTED:
        raise ValueError(
            f"Unknown indicator {indicator!r}; supported: {', '.join(sorted(_SUPPORTED))}"
        )

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    if name == "close_50_sma":
        return close.rolling(50).mean()
    if name == "close_200_sma":
        return close.rolling(200).mean()
    if name == "close_10_ema":
        return close.ewm(span=10, adjust=False).mean()

    if name in {"macd", "macds", "macdh"}:
        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal = macd_line.ewm(span=9, adjust=False).mean()
        if name == "macd":
            return macd_line
        if name == "macds":
            return signal
        return macd_line - signal  # macdh

    if name == "rsi":
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / loss.replace(0, pd.NA)
        return 100 - (100 / (1 + rs))

    if name in {"boll", "boll_ub", "boll_lb"}:
        mid = close.rolling(20).mean()
        std = close.rolling(20).std()
        if name == "boll":
            return mid
        if name == "boll_ub":
            return mid + 2 * std
        return mid - 2 * std

    if name == "atr":
        prev_close = close.shift(1)
        tr = pd.concat([
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(14).mean()

    if name == "vwma":
        return (close * volume).rolling(20).sum() / volume.rolling(20).sum()

    raise AssertionError(f"unhandled indicator {indicator!r}")


def render_indicator_markdown(df: pd.DataFrame, indicator: str, look_back: int = 30) -> str:
    """Render the trailing ``look_back`` rows of an indicator as markdown."""
    if df.empty:
        return f"No data available to compute {indicator}."

    series = compute(df, indicator).tail(look_back)
    times = df["time"].tail(look_back)
    closes = df["close"].tail(look_back)

    header = f"| Time (UTC) | Close | {indicator} |"
    sep = "|---|---:|---:|"
    body_rows = []
    for t, c, v in zip(times, closes, series):
        v_text = f"{v:,.4f}" if pd.notna(v) else "—"
        body_rows.append(f"| {t.strftime('%Y-%m-%d %H:%M')} | {c:,.2f} | {v_text} |")
    return "\n".join([header, sep, *body_rows])
