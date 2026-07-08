"""Bar replay: turn a historical bar series into per-step MarketSnapshots.

Lookahead safety is structural: the snapshot at step ``i`` contains only
bars up to and including ``i``, its indicators are computed from exactly
that window, and ``as_of`` is bar i's start. Fills happen on bar ``i+1``
in the engine — the decision never sees its own fill bar.

Works for any contract Timeframe (1m..1w). Tick data is pending the paid
microstructure feeds in docs/DATA_SOURCES.md.
"""

from __future__ import annotations

from collections.abc import Sequence

from tradingagents.contracts import AssetClass, MarketSnapshot, OHLCVBar
from tradingagents.pro.ingestion.indicators import DEFAULT_INDICATOR_NAMES, compute_indicators


class BarReplay:
    def __init__(
        self,
        symbol: str,
        asset: AssetClass,
        bars: Sequence[OHLCVBar],
        window: int = 250,
        indicator_names: Sequence[str] = DEFAULT_INDICATOR_NAMES,
    ):
        bars = sorted(bars, key=lambda b: b.start)
        timeframes = {b.timeframe for b in bars}
        if len(timeframes) > 1:
            raise ValueError("replay drives on a single timeframe series")
        if len(bars) < 3:
            raise ValueError("need at least 3 bars to replay")
        self.symbol = symbol
        self.asset = asset
        self.bars = list(bars)
        self.window = window
        self.indicator_names = tuple(indicator_names)

    def __len__(self) -> int:
        return len(self.bars)

    def snapshot_at(self, i: int) -> MarketSnapshot:
        """Snapshot as of the close of bar ``i`` — bars after i do not exist."""
        if not 0 <= i < len(self.bars):
            raise IndexError(i)
        visible = self.bars[max(0, i + 1 - self.window) : i + 1]
        return MarketSnapshot(
            symbol=self.symbol,
            asset=self.asset,
            as_of=visible[-1].start,
            bars=visible,
            indicators=compute_indicators(visible, self.indicator_names),
        )
