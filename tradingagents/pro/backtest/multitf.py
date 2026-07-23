"""Multi-timeframe support for backtests (roadmap P3 / architecture track T4).

A strategy drives on one (lower) timeframe but often wants to consult a higher
one — "only go long when the daily trend is up." The danger is look-ahead: at
an intraday bar you must NOT see the still-forming daily bar, only daily bars
that have already CLOSED. This module aggregates the lower-timeframe (LTF)
series into higher-timeframe (HTF) bars and exposes, at any LTF timestamp,
exactly the HTF bars whose period has fully elapsed by then.

``MultiTimeframeReplay`` wraps a base ``BarReplay`` and hands a strategy a
look-ahead-safe HTF ``MarketSnapshot`` (bars + windowed indicators, built only
from completed HTF bars). The engine populates ``StrategyContext.htf`` from it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from tradingagents.contracts import MarketSnapshot, OHLCVBar, Timeframe
from tradingagents.pro.ingestion.indicators import (
    DEFAULT_INDICATOR_NAMES,
    compute_indicators,
)

HTF_SECONDS: dict[Timeframe, int] = {
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
    Timeframe.W1: 604800,
}


def _bucket_start(ts: datetime, htf: Timeframe) -> datetime:
    """The start of the HTF period containing ``ts``. Weeks anchor on Monday
    00:00; days on 00:00; intraday periods floor within the day so boundaries
    are stable (e.g. 4h → 00/04/08/12/16/20)."""
    midnight = ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if htf == Timeframe.W1:
        return (midnight - timedelta(days=ts.weekday()))
    if htf == Timeframe.D1:
        return midnight
    period = HTF_SECONDS[htf]
    elapsed = int((ts - midnight).total_seconds())
    return midnight + timedelta(seconds=(elapsed // period) * period)


def aggregate_htf(bars: Sequence[OHLCVBar], htf: Timeframe) -> list[OHLCVBar]:
    """Group an LTF series into HTF bars (open=first, high=max, low=min,
    close=last, volume=sum) keyed by HTF period. ``htf`` must be strictly
    coarser than the input bars' timeframe."""
    if not bars:
        return []
    ltf = bars[0].timeframe
    if HTF_SECONDS[htf] <= HTF_SECONDS[ltf]:
        raise ValueError(
            f"htf {htf.value} must be coarser than the bar timeframe {ltf.value}")
    buckets: dict[datetime, list[OHLCVBar]] = {}
    order: list[datetime] = []
    for bar in sorted(bars, key=lambda b: b.start):
        key = _bucket_start(bar.start, htf)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(bar)
    out: list[OHLCVBar] = []
    for key in order:
        group = buckets[key]
        out.append(OHLCVBar(
            timeframe=htf, start=key,
            open=group[0].open,
            high=max(b.high for b in group),
            low=min(b.low for b in group),
            close=group[-1].close,
            volume=sum(b.volume for b in group)))
    return out


def htf_bars_as_of(htf_bars: Sequence[OHLCVBar], as_of: datetime) -> list[OHLCVBar]:
    """The HTF bars whose period has fully ELAPSED by ``as_of`` — i.e.
    ``bucket_start + period <= as_of``. This is the look-ahead-safe set: a
    still-forming HTF bar (its period not yet complete) is never returned."""
    done: list[OHLCVBar] = []
    for bar in htf_bars:
        end = bar.start + timedelta(seconds=HTF_SECONDS[bar.timeframe])
        if end <= as_of:
            done.append(bar)
    return done


class MultiTimeframeReplay:
    """Wrap a base (LTF) ``BarReplay`` and expose completed higher-timeframe
    snapshots as of any base-bar index. The HTF series are precomputed once;
    ``htf_snapshot`` slices only the already-closed HTF bars, so it is
    look-ahead-safe by the same rule as the single-timeframe path."""

    def __init__(self, base, htf_timeframes: Sequence[Timeframe],
                 window: int = 120,
                 indicator_names: Sequence[str] = DEFAULT_INDICATOR_NAMES):
        self.base = base
        self.window = window
        self.indicator_names = tuple(indicator_names)
        self._htf: dict[Timeframe, list[OHLCVBar]] = {}
        for tf in htf_timeframes:
            self._htf[tf] = aggregate_htf(base.bars, tf)

    @property
    def timeframes(self) -> tuple[Timeframe, ...]:
        return tuple(self._htf)

    def htf_snapshot(self, i: int, tf: Timeframe) -> MarketSnapshot | None:
        """Look-ahead-safe HTF snapshot as of base bar ``i``'s start, or None
        when no HTF bar has closed yet. Indicators are computed over the
        completed HTF window only (never over a forming or future bar)."""
        htf_bars = self._htf.get(tf)
        if not htf_bars:
            return None
        as_of = self.base.bars[i].start
        completed = htf_bars_as_of(htf_bars, as_of)
        if not completed:
            return None
        visible = completed[-self.window:]
        return MarketSnapshot(
            symbol=self.base.symbol,
            asset=self.base.asset,
            as_of=visible[-1].start,
            bars=visible,
            indicators=compute_indicators(visible, self.indicator_names),
            macro=[], onchain=[], news=[],
            missing_feeds=["htf-aggregated"],
        )

    def htf_map(self, i: int) -> dict[Timeframe, MarketSnapshot]:
        """All configured HTF snapshots available at base bar ``i`` (skips
        timeframes with no closed bar yet). Ready to drop into
        ``StrategyContext.htf``."""
        out: dict[Timeframe, MarketSnapshot] = {}
        for tf in self._htf:
            snap = self.htf_snapshot(i, tf)
            if snap is not None:
                out[tf] = snap
        return out


__all__ = ["MultiTimeframeReplay", "aggregate_htf", "htf_bars_as_of"]
