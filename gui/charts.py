"""Ticker vs index comparison + realised-return tables for a run.

Pulls daily OHLCV from yfinance (already a project dep), normalises to a
common starting price = 100 at the trade date, and lets the user see the
ticker against SPY (and optionally QQQ) over multiple windows.

Two views:
- **Forward**: from the trade date out to today (or as far as data exists).
  Shows what actually happened *if you'd taken the trade* — the most
  useful comparison.
- **Backward**: trailing N months ending on the trade date. Shows what
  the analysis was looking at when the recommendation was made.

For trade dates in the future, only the backward view exists.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import streamlit as st
import yfinance as yf


_INDEX_TICKERS = {
    "SPY": "SPDR S&P 500 ETF (broad market)",
    "QQQ": "Invesco QQQ (Nasdaq-100)",
}

_WINDOW_DAYS = {
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
}


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _fetch_close_cached(symbol: str, start_iso: str, end_iso: str) -> Optional[pd.Series]:
    """Cached yfinance fetch keyed by (symbol, date range).

    Streamlit reruns the whole page on every interaction; without caching,
    every refresh re-hits Yahoo over the network. TTL is 6 hours — long
    enough that intraday flips don't trigger refetches, short enough that
    end-of-day data is fresh by morning.
    """
    try:
        df = yf.Ticker(symbol).history(start=start_iso, end=end_iso)
        if df.empty:
            return None
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        return df["Close"].rename(symbol)
    except Exception:
        return None


def _fetch_close(symbol: str, start: date, end: date) -> Optional[pd.Series]:
    return _fetch_close_cached(symbol, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))


def build_comparison_frame(ticker: str, trade_date: str | date,
                          *, days_back: int, days_forward: int,
                          benchmarks: Iterable[str] = ("SPY", "QQQ"),
                          ) -> Optional[pd.DataFrame]:
    """Wrapper that normalises args to hashable types so the cached
    inner function can do its job."""
    td = trade_date if isinstance(trade_date, str) else trade_date.isoformat()
    return _build_comparison_frame_cached(
        ticker.upper(), td, int(days_back), int(days_forward),
        tuple(benchmarks),
    )


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _build_comparison_frame_cached(ticker: str, trade_date: str,
                                  days_back: int, days_forward: int,
                                  benchmarks: Tuple[str, ...],
                                  ) -> Optional[pd.DataFrame]:
    """Return a DataFrame indexed by date with ticker + benchmark columns,
    each normalised so the trade date sits at value 100."""
    td = _parse_date(trade_date)
    start = td - timedelta(days=days_back + 5)
    end = min(td + timedelta(days=days_forward + 5), date.today() + timedelta(days=1))

    series: Dict[str, pd.Series] = {}
    for sym in [ticker, *benchmarks]:
        s = _fetch_close(sym, start, end)
        if s is not None and len(s) >= 2:
            series[sym] = s

    if ticker not in series:
        return None

    df = pd.concat(series, axis=1).dropna(how="all").ffill()
    if df.empty:
        return None

    # Normalise to 100 at the trade date (or the first row >= trade date).
    td_ts = pd.Timestamp(td)
    pivot_idx = df.index[df.index >= td_ts]
    if len(pivot_idx) == 0:
        # Trade date is in the future — pivot on the last available row.
        pivot = df.iloc[-1]
    else:
        pivot = df.loc[pivot_idx[0]]

    normalised = df.divide(pivot).multiply(100.0)
    return normalised


def realised_returns_table(ticker: str, trade_date: str | date,
                          windows: Optional[Dict[str, int]] = None,
                          ) -> Optional[pd.DataFrame]:
    """Cache-friendly wrapper — see ``_realised_returns_cached``."""
    td = trade_date if isinstance(trade_date, str) else trade_date.isoformat()
    if windows is None:
        windows = _WINDOW_DAYS
    return _realised_returns_cached(ticker.upper(), td,
                                    tuple(sorted(windows.items())))


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _realised_returns_cached(ticker: str, trade_date: str,
                             windows_tuple: Tuple[Tuple[str, int], ...],
                             ) -> Optional[pd.DataFrame]:
    windows: Dict[str, int] = dict(windows_tuple)
    """Compute (raw return, return vs SPY) for the ticker over each window
    that has enough forward data. Returns ``None`` if the trade date is
    too recent for any window to have closed."""
    td = _parse_date(trade_date)
    today = date.today()
    if td >= today:
        return None

    rows: List[Dict[str, object]] = []
    for label, days in windows.items():
        end_target = td + timedelta(days=days)
        if end_target > today:
            continue
        # Pull a small buffer for weekends/holidays.
        end_buffered = end_target + timedelta(days=7)
        start_buffered = td - timedelta(days=2)
        ticker_close = _fetch_close(ticker, start_buffered, end_buffered)
        spy_close = _fetch_close("SPY", start_buffered, end_buffered)
        if ticker_close is None or spy_close is None or len(ticker_close) < 2 or len(spy_close) < 2:
            continue
        try:
            t_start = ticker_close.iloc[0]
            t_end = ticker_close.asof(pd.Timestamp(end_target))
            s_start = spy_close.iloc[0]
            s_end = spy_close.asof(pd.Timestamp(end_target))
            if pd.isna(t_end) or pd.isna(s_end):
                continue
            raw = (t_end - t_start) / t_start
            spy = (s_end - s_start) / s_start
            rows.append({
                "Window": label,
                f"{ticker} return": f"{raw * 100:+.2f}%",
                "SPY return": f"{spy * 100:+.2f}%",
                "Alpha vs SPY": f"{(raw - spy) * 100:+.2f}%",
            })
        except Exception:
            continue
    if not rows:
        return None
    return pd.DataFrame(rows)


def benchmark_labels() -> Dict[str, str]:
    return dict(_INDEX_TICKERS)
