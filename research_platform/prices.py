"""Daily final closes over a date range, for scoring and simulation.

These are read after the fact on purpose: the scorecard and the paper portfolio look
at what happened *after* each analysis date. No decision is ever made from them.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date as Date, datetime

import pandas as pd

# (symbol, start YYYY-MM-DD, end YYYY-MM-DD) -> closes indexed by calendar day, ascending
PriceLookup = Callable[[str, str, str], pd.Series]


def yahoo_closes(symbol: str, start: str, end: str) -> pd.Series:
    """Final closes from ``start`` to ``end`` inclusive, through the repo's data layer."""
    from tradingagents.dataflows.vendors.yahoo.market import get_final_closes

    days = (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days
    closes = get_final_closes(symbol, end, max(days, 1))
    return closes[closes.index >= pd.Timestamp(start)].sort_index()


class CachedPrices:
    """Fetch each symbol once over the widest range asked for, then slice."""

    def __init__(self, lookup: PriceLookup = yahoo_closes):
        self._lookup = lookup
        self._cache: dict[str, tuple[str, str, pd.Series]] = {}

    def __call__(self, symbol: str, start: str, end: str) -> pd.Series:
        cached = self._cache.get(symbol)
        if cached is None or start < cached[0] or end > cached[1]:
            lo = min(start, cached[0]) if cached else start
            hi = max(end, cached[1]) if cached else end
            self._cache[symbol] = cached = (lo, hi, self._lookup(symbol, lo, hi))
        series = cached[2]
        return series[(series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))]


def today() -> str:
    return Date.today().strftime("%Y-%m-%d")
