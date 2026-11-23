"""Score recorded signals against what prices did afterwards.

For a signal on analysis date D:

- entry is the first final close strictly after D, the first price anyone acting on
  the decision could have had (the decision uses closes up to D);
- the return over h trading days is close[entry + h] / close[entry] - 1;
- the benchmark (the instrument's regional benchmark, as the memory log settles
  against) is read on or before the same two dates, and alpha = return - benchmark return;
- a Buy or Overweight claims alpha > 0, an Underweight or Sell claims alpha < 0, and a
  Hold claims no direction, so it has no hit rate.

A horizon that has not fully traded yet is pending, never estimated.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from statistics import mean, median

import pandas as pd

from research_platform.config import SCORE_HORIZONS
from research_platform.prices import CachedPrices, PriceLookup, today
from research_platform.store import RATINGS, Signal

DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}


@dataclass
class Outcome:
    ticker: str
    date: str
    rating: str
    horizon: int
    entry_date: str | None = None
    exit_date: str | None = None
    ret: float | None = None
    benchmark: str | None = None
    benchmark_ret: float | None = None
    note: str = ""

    @property
    def settled(self) -> bool:
        return self.ret is not None

    @property
    def alpha(self) -> float | None:
        if self.ret is None or self.benchmark_ret is None:
            return None
        return self.ret - self.benchmark_ret

    @property
    def hit(self) -> bool | None:
        direction = DIRECTION.get(self.rating, 0)
        if not direction or self.alpha is None:
            return None
        return self.alpha * direction > 0


@dataclass
class Bucket:
    rating: str
    horizon: int
    count: int
    hit_rate: float | None
    mean_return: float
    mean_alpha: float | None
    median_alpha: float | None


@dataclass
class Scorecard:
    outcomes: list[Outcome]
    buckets: list[Bucket] = field(default_factory=list)
    spread: dict[int, float | None] = field(default_factory=dict)   # bullish minus bearish mean alpha

    def pending(self, horizon: int) -> int:
        return sum(1 for o in self.outcomes if o.horizon == horizon and not o.settled)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "ticker": o.ticker, "date": o.date, "rating": o.rating, "horizon_days": o.horizon,
            "entry": o.entry_date, "exit": o.exit_date, "return": o.ret, "benchmark": o.benchmark,
            "benchmark_return": o.benchmark_ret, "alpha": o.alpha, "hit": o.hit, "note": o.note,
        } for o in self.outcomes])

    def summary_frame(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "rating": b.rating, "horizon_days": b.horizon, "n": b.count, "hit_rate": b.hit_rate,
            "mean_return": b.mean_return, "mean_alpha": b.mean_alpha, "median_alpha": b.median_alpha,
        } for b in self.buckets])

    def render(self) -> str:
        lines = []
        for horizon in sorted({o.horizon for o in self.outcomes}):
            lines.append(f"{horizon} trading days (pending: {self.pending(horizon)})")
            for b in (b for b in self.buckets if b.horizon == horizon):
                hit = f"hit {b.hit_rate:.0%}" if b.hit_rate is not None else "no direction claimed"
                alpha = f"mean alpha {b.mean_alpha:+.2%}" if b.mean_alpha is not None else "alpha n/a"
                lines.append(f"  {b.rating:<11} n={b.count:<3} {hit:<22} mean return {b.mean_return:+.2%}  {alpha}")
            spread = self.spread.get(horizon)
            if spread is not None:
                lines.append(f"  bullish minus bearish mean alpha: {spread:+.2%}")
        return "\n".join(lines) or "No signals to score yet."


def _benchmark_for(ticker: str, cfg: dict | None) -> str:
    from research_platform.config import platform_config
    from tradingagents.memory.settlement import resolve_benchmark

    return resolve_benchmark(ticker, cfg or platform_config())


def outcome(signal: Signal, horizon: int, closes: pd.Series, bench_closes: pd.Series | None,
            benchmark: str | None) -> Outcome:
    """One signal's result over ``horizon`` trading days, from closes starting at its date."""
    result = Outcome(signal.ticker, signal.date, signal.rating, horizon, benchmark=benchmark)
    after = closes[closes.index > pd.Timestamp(signal.date)]
    if after.empty:
        result.note = "no close after the analysis date yet"
        return result
    result.entry_date = f"{after.index[0]:%Y-%m-%d}"
    if len(after) <= horizon:
        result.note = f"{len(after) - 1} of {horizon} trading days so far"
        return result
    entry, exit_ = after.iloc[0], after.iloc[horizon]
    result.exit_date = f"{after.index[horizon]:%Y-%m-%d}"
    result.ret = float(exit_ / entry - 1)
    if bench_closes is None or bench_closes.empty:
        result.note = "benchmark prices unavailable"
        return result
    b0, b1 = bench_closes.asof(after.index[0]), bench_closes.asof(after.index[horizon])
    if pd.isna(b0) or pd.isna(b1):
        result.note = "benchmark has no close on or before the entry date"
        return result
    result.benchmark_ret = float(b1 / b0 - 1)
    return result


def score(signals: Iterable[Signal], prices: PriceLookup | None = None,
          horizons: tuple[int, ...] = SCORE_HORIZONS, cfg: dict | None = None,
          benchmark_of=None, end: str | None = None) -> Scorecard:
    """Score every usable signal at every horizon."""
    prices = prices or CachedPrices()
    benchmark_of = benchmark_of or (lambda t: _benchmark_for(t, cfg))
    end = end or today()
    outcomes = []
    for signal in signals:
        if not signal.ok:
            continue
        try:
            closes = prices(signal.ticker, signal.date, end)
        except Exception as exc:  # noqa: BLE001 - one missing history leaves that signal unscored
            outcomes.extend(Outcome(signal.ticker, signal.date, signal.rating, h,
                                    note=f"prices unavailable: {exc}") for h in horizons)
            continue
        benchmark = benchmark_of(signal.ticker)
        try:
            # A week earlier, so the benchmark has a close on or before the first entry.
            start = (pd.Timestamp(signal.date) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            bench = prices(benchmark, start, end)
        except Exception:  # noqa: BLE001
            bench = None
        outcomes.extend(outcome(signal, h, closes, bench, benchmark) for h in horizons)
    return aggregate(outcomes, horizons)


def aggregate(outcomes: list[Outcome], horizons: tuple[int, ...] = SCORE_HORIZONS) -> Scorecard:
    card = Scorecard(outcomes=outcomes)
    for horizon in horizons:
        settled = [o for o in outcomes if o.horizon == horizon and o.settled]
        for rating in RATINGS:
            group = [o for o in settled if o.rating == rating]
            if not group:
                continue
            alphas = [o.alpha for o in group if o.alpha is not None]
            hits = [o.hit for o in group if o.hit is not None]
            card.buckets.append(Bucket(
                rating=rating, horizon=horizon, count=len(group),
                hit_rate=(sum(hits) / len(hits)) if hits else None,
                mean_return=mean(o.ret for o in group),
                mean_alpha=mean(alphas) if alphas else None,
                median_alpha=median(alphas) if alphas else None,
            ))
        bull = [o.alpha for o in settled if DIRECTION[o.rating] > 0 and o.alpha is not None]
        bear = [o.alpha for o in settled if DIRECTION[o.rating] < 0 and o.alpha is not None]
        card.spread[horizon] = (mean(bull) - mean(bear)) if bull and bear else None
    return card
