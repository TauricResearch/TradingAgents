"""Portfolio replay (roadmap P3 / architecture track T4): a k-way timestamp
merge of per-symbol ``BarReplay``s onto one master clock.

The master timeline is the sorted union of every symbol's bar starts. At a
master step, a symbol is *active* iff it has a bar whose start equals the
step's timestamp — i.e. a fresh bar just closed for it, so it gets a decision
opportunity. Each symbol's snapshot is taken from its OWN ``BarReplay`` as of
that timestamp, so per-symbol look-ahead safety is inherited unchanged from
the single-symbol path (the snapshot at a symbol's local index i sees only
that symbol's bars <= i).

Symbols on different timeframes merge naturally: a 1h symbol simply has more
timeline points than a 1d symbol, and between a slow symbol's bars its most
recent closed bar stays available for marking open positions — never a future
one. Symbols that have not started trading yet at a given step are absent from
it (``local_index`` returns None), so a late-listed asset contributes nothing
until its first bar.

This module is the merge primitive only; the multi-symbol engine loop,
capital allocator, and portfolio-heat cap build on top of it.
"""

from __future__ import annotations

import bisect
from collections.abc import Mapping, Sequence
from datetime import datetime

from tradingagents.contracts import MarketSnapshot, OHLCVBar
from tradingagents.pro.backtest.data import BarReplay


class PortfolioReplay:
    def __init__(self, replays: Mapping[str, BarReplay] | Sequence[BarReplay]):
        items = (list(replays.items()) if isinstance(replays, Mapping)
                 else [(r.symbol, r) for r in replays])
        if not items:
            raise ValueError("portfolio replay needs at least one symbol")
        self._replays: dict[str, BarReplay] = {}
        for symbol, replay in items:
            if symbol in self._replays:
                raise ValueError(f"duplicate symbol {symbol!r} in portfolio replay")
            self._replays[symbol] = replay
        self.symbols: tuple[str, ...] = tuple(self._replays)

        # per-symbol sorted bar starts (for as-of bisect) + a start->index map
        # (for O(1) "is this symbol active at this exact timestamp") + the
        # sorted union of all starts as the master clock.
        self._starts: dict[str, list[datetime]] = {}
        self._start_index: dict[str, dict[datetime, int]] = {}
        union: set[datetime] = set()
        for symbol, replay in self._replays.items():
            starts = [b.start for b in replay.bars]  # BarReplay sorts on init
            self._starts[symbol] = starts
            self._start_index[symbol] = {ts: k for k, ts in enumerate(starts)}
            union.update(starts)
        self.timeline: list[datetime] = sorted(union)

    def __len__(self) -> int:
        return len(self.timeline)

    def replay(self, symbol: str) -> BarReplay:
        return self._replays[symbol]

    def timestamp_at(self, step: int) -> datetime:
        return self.timeline[step]

    def active_symbols_at(self, step: int) -> tuple[str, ...]:
        """Symbols with a bar closing exactly at this step's timestamp — the
        ones eligible for a fresh decision. Preserves construction order."""
        ts = self.timeline[step]
        return tuple(s for s in self.symbols if ts in self._start_index[s])

    def local_index(self, symbol: str, step: int) -> int | None:
        """The symbol's most-recent bar index at or before the step's
        timestamp; None when the symbol has no bar yet (started later)."""
        ts = self.timeline[step]
        starts = self._starts[symbol]
        pos = bisect.bisect_right(starts, ts) - 1
        return pos if pos >= 0 else None

    def bar_at(self, symbol: str, step: int) -> OHLCVBar | None:
        """The symbol's most-recent closed bar at/before the step (for marking
        open positions), or None if it has not started."""
        i = self.local_index(symbol, step)
        return self._replays[symbol].bars[i] if i is not None else None

    def snapshot_at(self, symbol: str, step: int) -> MarketSnapshot | None:
        """Look-ahead-safe snapshot for the symbol as of the step's timestamp,
        or None if the symbol has not started. Delegates to the symbol's own
        BarReplay, so indicator/warm-up/corpus discipline is identical to a
        single-symbol run."""
        i = self.local_index(symbol, step)
        return self._replays[symbol].snapshot_at(i) if i is not None else None


__all__ = ["PortfolioReplay"]
