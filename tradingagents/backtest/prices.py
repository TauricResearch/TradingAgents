"""Price-data abstraction for the F2 backtest harness.

A ``PriceSource`` is anything that can return historical OHLC bars for a
ticker over a window at a given resolution. The ``PriceFallbackChain``
(Task 3) tries each registered source in priority order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import List, Protocol, Set, Tuple, runtime_checkable


class Resolution(StrEnum):
    DAILY = "1d"
    ONE_MIN = "1m"


@dataclass(frozen=True)
class Bars:
    """A frozen container of (timestamp, close_price) tuples for one ticker."""
    ticker: str
    resolution: Resolution
    bars: List[Tuple[datetime, float]]
    source: str  # name of the producing PriceSource, e.g. "yfinance"


class PriceDataUnavailable(Exception):
    """Raised when every source in the fallback chain failed.

    Caught by the harness, which then marks the affected forward test
    ``status=errored`` with ``errored_sources`` recorded in metrics.
    """

    def __init__(self, ticker: str, start: date, end: date,
                 tried_sources: List[str]):
        self.ticker = ticker
        self.start = start
        self.end = end
        self.tried_sources = list(tried_sources)
        super().__init__(
            f"No price data for {ticker} {start}..{end}; "
            f"tried sources: {self.tried_sources}"
        )


@runtime_checkable
class PriceSource(Protocol):
    """One adapter to a price-data provider."""
    name: str
    supports: Set[Resolution]

    def get_bars(
        self,
        ticker: str,
        start: date,
        end: date,
        resolution: Resolution,
    ) -> Bars:
        """Fetch close-price bars for ``ticker`` from ``start`` to ``end``.

        Returns a ``Bars`` with ``source = self.name``. Raises if the source
        cannot produce data for this window/resolution.
        """
        ...


class PriceFallbackChain:
    """Ordered chain of ``PriceSource`` implementations.

    ``get_bars()`` tries each source that supports the requested resolution
    in order; returns the first success. Sources whose ``supports`` does
    not include the resolution are skipped (never called). Raises
    ``PriceDataUnavailable`` if every supporting source fails or no source
    supports the resolution.
    """

    def __init__(self, sources: List[PriceSource]):
        self._sources = list(sources)

    def get_bars(
        self,
        ticker: str,
        start: date,
        end: date,
        resolution: Resolution = Resolution.DAILY,
    ) -> Bars:
        tried: List[str] = []
        for src in self._sources:
            if resolution not in src.supports:
                continue
            tried.append(src.name)
            try:
                return src.get_bars(ticker, start, end, resolution)
            except Exception:  # noqa: BLE001 — any failure → try next source
                continue
        raise PriceDataUnavailable(ticker, start, end, tried)
