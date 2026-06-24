"""In-memory replacement for yfinance for tests."""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


class _FakeSeries:
    def __init__(self, prices: list[float]):
        self._prices = list(prices)

    @property
    def empty(self) -> bool:
        return len(self._prices) == 0

    def __getitem__(self, key):
        # support .loc["Close"] and .iloc[-1] style access; return self
        return self

    def dropna(self) -> _FakeSeries:
        # fake has no NaN values; return a copy
        return _FakeSeries(self._prices)

    def tail(self, n: int) -> _FakeSeries:
        return _FakeSeries(self._prices[-n:])

    def __iter__(self):
        # production does list(series.dropna().tail(30)); without __iter__
        # Python falls back to the legacy __getitem__ protocol, which our
        # fake satisfies forever (no IndexError) and hangs.
        return iter(self._prices)


class _FakeDf:
    def __init__(self, by_ticker: dict[str, list[float]]):
        self._by = dict(by_ticker)

    def __getitem__(self, key):
        # production calls df["Close"] in single-ticker mode and df[ticker]
        # in multi-ticker mode. We detect the column-name call by checking
        # whether `key` is in the ticker dict; if not, return a single-ticker
        # series if exactly one ticker is present, else empty.
        if key in self._by:
            return _FakeSeries(self._by[key])
        if len(self._by) == 1:
            return _FakeSeries(next(iter(self._by.values())))
        return _FakeSeries([])


def make_fake_download(by_ticker: dict[str, list[float]]):
    def _download(tickers: Iterable[str] | str, **kwargs):
        if isinstance(tickers, str):
            return _FakeDf({tickers: by_ticker.get(tickers, [])})
        return _FakeDf({t: by_ticker.get(t, []) for t in tickers})
    return _download


def make_fake_ticker_with_history(df: pd.DataFrame) -> type:
    """Return a stand-in for ``yf.Ticker`` whose ``.history()`` returns ``df``.

    The class records every ``.history`` call on ``.calls`` so cache-hit
    assertions can count yfinance invocations.
    """

    class _FakeTicker:
        calls = 0

        def history(self, **kwargs):
            type(self).calls += 1
            return df

    return _FakeTicker


def make_history_df(
    start,  # datetime (stringified to keep this file stdlib-friendly)
    n: int,
    *,
    base: float = 100.0,
    step: float = 0.5,
    freq: str = "1h",
) -> pd.DataFrame:
    """Build a deterministic OHLCV DataFrame starting at ``start`` with ``n`` rows.

    Columns: Open, High, Low, Close, Volume. Index: tz-aware UTC
    ``DatetimeIndex`` with the given ``freq``.
    """
    idx = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "Open":  [base + i * step for i in range(n)],
            "High":  [base + i * step + 0.1 for i in range(n)],
            "Low":   [base + i * step - 0.1 for i in range(n)],
            "Close": [base + i * step for i in range(n)],
            "Volume": [1000.0 for _ in range(n)],
        },
        index=idx,
    )
