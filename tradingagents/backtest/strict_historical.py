"""Look-ahead assertion for back-dated backtest runs (R-F2-1).

When the harness runs a forward test with ``start_date < today``, every
bar returned by the price layer MUST have ``timestamp.date() <= cutoff``
(typically ``cutoff = end_date``). A bar past the cutoff means a data
source ignored the cutoff and leaked future data into the agent's view,
which would silently inflate measured alpha.
"""

from __future__ import annotations

from datetime import date
from typing import Set

from tradingagents.backtest.prices import Bars, PriceSource, Resolution


class LookaheadDataError(Exception):
    """A PriceSource returned a bar past the configured cutoff."""


def assert_no_lookahead(bars: Bars, *, cutoff: date) -> None:
    """Raise ``LookaheadDataError`` if any bar's date is past ``cutoff``."""
    for ts, _close in bars.bars:
        if ts.date() > cutoff:
            raise LookaheadDataError(
                f"Source {bars.source!r} returned a bar at {ts.isoformat()} "
                f"for {bars.ticker} which is past the cutoff {cutoff.isoformat()}. "
                "This is a look-ahead leak — fix the source or stub it for backtests."
            )


class StrictHistoricalChain:
    """Wraps any object with ``get_bars(...)`` and asserts no look-ahead."""

    def __init__(self, inner, *, cutoff: date):
        self._inner = inner
        self._cutoff = cutoff

    # `supports` lookup falls through for callers that need it (PriceFallbackChain)
    @property
    def supports(self) -> Set[Resolution]:
        return getattr(self._inner, "supports", {Resolution.DAILY})

    @property
    def name(self) -> str:
        return f"strict({getattr(self._inner, 'name', 'inner')})"

    def get_bars(self, ticker, start, end, resolution) -> Bars:
        bars = self._inner.get_bars(ticker, start, end, resolution)
        assert_no_lookahead(bars, cutoff=self._cutoff)
        return bars
