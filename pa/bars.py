"""OHLCV bar loading and timeframe resampling for the PA engine.

Single source of truth for what a "bar" looks like inside ``pa``: a
``pandas.DataFrame`` indexed by tz-naive ``DatetimeIndex`` (one row per
bar) with float columns ``open``, ``high``, ``low``, ``close``, ``volume``.
Lowercased so downstream feature code never has to remember whether
yfinance emitted "Close" or "close".

The Brooks engine works on daily and weekly bars only — intraday is
explicitly out of scope for v1. ``fetch_bars`` returns daily bars by
default; pass ``timeframe="weekly"`` to get weekly bars resampled from
the daily series (Friday-anchored, the convention most chart tooling
uses).
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
import yfinance as yf

Timeframe = Literal["daily", "weekly"]

_OHLCV = ["open", "high", "low", "close", "volume"]


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase columns, drop tz, keep only OHLCV."""
    out = df.rename(columns=str.lower)
    out = out[[c for c in _OHLCV if c in out.columns]].copy()
    if isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    out.index.name = "date"
    return out.astype(float)


def resample_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Resample daily bars to weekly bars anchored on Friday.

    A weekly bar's open is Monday's open, close is Friday's close, high
    and low are the extrema of the week, volume is the sum. Weeks with
    no trading days are dropped.
    """
    if daily.empty:
        return daily
    weekly = daily.resample("W-FRI").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return weekly.dropna(subset=["open", "close"])


def fetch_bars(
    ticker: str,
    start: str,
    end: str,
    timeframe: Timeframe = "daily",
) -> pd.DataFrame:
    """Fetch OHLCV bars from yfinance.

    Args:
        ticker: ticker symbol (e.g. "NVDA").
        start: ISO date "YYYY-MM-DD" inclusive.
        end:   ISO date "YYYY-MM-DD" exclusive (yfinance convention).
        timeframe: "daily" (default) or "weekly".

    Daily bars come straight from yfinance with ``auto_adjust=True`` so
    the prices already reflect splits and dividends. Weekly bars are
    resampled from the daily series, which avoids yfinance's own weekly
    feed where the partial trailing week occasionally misbehaves.
    """
    if timeframe not in ("daily", "weekly"):
        raise ValueError(f"timeframe must be 'daily' or 'weekly', got {timeframe!r}")

    raw = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    if raw.empty:
        raise ValueError(f"no bars returned for {ticker} {start}->{end}")

    daily = _normalise(raw)
    return resample_weekly(daily) if timeframe == "weekly" else daily
