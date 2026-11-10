"""What the signals were worth on their own, apart from sizing and stops.

For every signal: the price when it was acted on and the price 1, 4 and 24 hours
later, as the return in the direction called (a Short earns when the price falls).
Grouped by coin, conviction and direction, that says which signals carry
information and over which horizon, and how often the model changes its mind.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from statistics import mean, median

from trader.evaluation.history import HOUR_MS, MINUTE_MS, HistoryStore
from trader.evaluation.replay import DIRECTIONS, Signal

HORIZONS = (1, 4, 24)  # hours


@dataclass(frozen=True)
class Outcome:
    signal: Signal
    price: float
    # horizon (hours) -> return in the direction called; for Flat the raw return
    # the account sat out. None when the store has no price that far ahead.
    returns: dict[int, float | None]

    @property
    def direction(self) -> str:
        return self.signal.signal or "None"


@dataclass(frozen=True)
class Row:
    group: str
    count: int
    hit_rate: dict[int, float | None]    # share of outcomes with a positive return
    mean_bps: dict[int, float | None]    # mean return in basis points
    median_bps: dict[int, float | None]


def price_at(store: HistoryStore, inst: str, at_ms: int) -> float | None:
    """Close of the last minute candle closed by ``at_ms``: the price a decision at
    ``at_ms`` would have been filled near. None when the store has no candle in the
    few minutes before (a gap, or history that ends earlier)."""
    bars = store.bars(inst, "1m", at_ms - 5 * MINUTE_MS, at_ms)
    return bars[-1].close if bars else None


def outcomes(
    store: HistoryStore, signals: Iterable[Signal], swap_of: dict[str, str],
    horizons: tuple[int, ...] = HORIZONS,
) -> list[Outcome]:
    """The outcomes of the signals with a direction or Flat, skipping coins not in
    ``swap_of`` (research key -> swap) and hours the store has no price for."""
    out = []
    for s in signals:
        inst = swap_of.get(s.coin)
        if inst is None or s.signal is None:
            continue
        decided = s.ts - s.ts % MINUTE_MS + MINUTE_MS
        p0 = price_at(store, inst, decided)
        if not p0:
            continue
        sign = 1.0 if s.signal == "Long" else -1.0 if s.signal == "Short" else 1.0
        rets: dict[int, float | None] = {}
        for h in horizons:
            p1 = price_at(store, inst, decided + h * HOUR_MS)
            rets[h] = None if p1 is None else sign * (p1 / p0 - 1)
        out.append(Outcome(s, p0, rets))
    return out


def summarize(items: Iterable[Outcome], key: Callable[[Outcome], str]) -> list[Row]:
    """One row per value of ``key``, in first-seen order."""
    groups: dict[str, list[Outcome]] = {}
    for o in items:
        groups.setdefault(key(o), []).append(o)
    rows = []
    for name, members in groups.items():
        horizons = sorted({h for o in members for h in o.returns})
        hit, avg, mid = {}, {}, {}
        for h in horizons:
            values = [o.returns[h] for o in members if o.returns.get(h) is not None]
            hit[h] = sum(1 for v in values if v > 0) / len(values) if values else None
            avg[h] = mean(values) * 10_000 if values else None
            mid[h] = median(values) * 10_000 if values else None
        rows.append(Row(name, len(members), hit, avg, mid))
    return rows


def by_coin(o: Outcome) -> str:
    return o.signal.coin


def by_direction(o: Outcome) -> str:
    return o.direction


def by_conviction(o: Outcome) -> str:
    return f"信心 {o.signal.conviction}" if o.signal.conviction is not None else "信心 —"


def directional(items: Iterable[Outcome]) -> list[Outcome]:
    return [o for o in items if o.direction in DIRECTIONS]


@dataclass(frozen=True)
class Flips:
    coin: str
    hours: int          # signals with any value
    long: int
    short: int
    flat: int
    missing: int        # hours that produced no signal
    reversals: int      # Long right after Short or the other way, Flat between not counted
    changes: int        # any change of label between consecutive signals
    mean_run: float     # mean length, in signals, of a run of the same label


def flips(signals: Iterable[Signal]) -> list[Flips]:
    """How often each coin's signal changed, in time order."""
    by: dict[str, list[Signal]] = {}
    for s in sorted(signals, key=lambda s: s.ts):
        by.setdefault(s.coin, []).append(s)
    out = []
    for coin, series in by.items():
        labels = [s.signal for s in series]
        present = [label for label in labels if label is not None]
        reversals = changes = 0
        runs: list[int] = []
        last_direction = previous = None
        for label in present:
            if label == previous:
                runs[-1] += 1
            else:
                runs.append(1)
                changes += previous is not None
            previous = label
            if label in DIRECTIONS:
                if last_direction and label != last_direction:
                    reversals += 1
                last_direction = label
        out.append(Flips(
            coin=coin, hours=len(labels), long=labels.count("Long"), short=labels.count("Short"),
            flat=labels.count("Flat"), missing=labels.count(None), reversals=reversals,
            changes=changes, mean_run=mean(runs) if runs else 0.0,
        ))
    return out

