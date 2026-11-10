"""Rerunning the intraday signal over history (Issue #28).

The live account records 72 signals a day. To judge the rules on months rather
than days, the same ``Signaler`` (same prompt, same model) is asked hour by hour
what it would have said, seeing only what the history store holds as of that hour,
while the engine trades its answers so the prompt's "current position" is the one
the rules would have held. Every answer is cached in a ledger file keyed by hour
and coin: a rerun resumes where it stopped and never pays for an hour twice, and
the cache is itself a signal source for ``replay`` and the signal study.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

from trader.evaluation.history import HistoryStore
from trader.evaluation.market import HistoricalOKX
from trader.evaluation.replay import Result, Signal, replay
from trader.intraday.settings import DEFAULT_PARAMS, Params
from trader.intraday.signal import Signaler
from trader.intraday.types import SignalResult
from trader.ledger import Ledger, Position
from trader.settings import WATCHLIST, Coin

MAX_EMPTY_HOURS = 3  # this many hours in a row without one usable signal stops the rerun
RETRIES = 4          # more tries of an hour whose calls failed without costing anything
RETRY_PAUSE = 15.0   # seconds before the first retry; doubles each time


class BudgetExhausted(RuntimeError):
    """The run's spending reached its budget before the period was done."""


class NothingWorks(RuntimeError):
    """MAX_EMPTY_HOURS hours in a row produced no signal: the model or the history is
    not answering, and paying on is pointless."""


@dataclass
class Stats:
    hours: int = 0          # hours decided (cached or made)
    calls: int = 0          # model calls made in this run
    cached: int = 0         # signals taken from the cache
    failures: int = 0       # calls that produced no signal
    spent: float = 0.0      # USD spent in this run
    errors: list[str] = field(default_factory=list)


class Rerun:
    """The ``signaler`` hook of ``replay``: makes the hour's signals with the live
    Signaler against the historical market and caches them in ``cache``."""

    def __init__(
        self, signaler: Signaler, market: HistoricalOKX, cache: Ledger, *,
        watchlist: tuple[Coin, ...] = WATCHLIST, budget_usd: float | None = None,
        workers: int = 3, log=None, sleep: Callable[[float], None] = time.sleep,
    ):
        self.signaler = signaler
        self.market = market
        self.cache = cache
        self.watchlist = watchlist
        self.budget = budget_usd
        self.workers = max(1, workers)
        self.log = log or (lambda message: None)
        self.sleep = sleep
        self.stats = Stats()
        self.empty_hours = 0
        self.clock = datetime.now(UTC)
        signaler.now_fn = lambda: self.clock  # bounds the research's trade date
        if signaler.okx is not market:
            raise ValueError("the signaler must read the same historical market the engine does")
        self._check_fingerprint()

    def _check_fingerprint(self) -> None:
        """A cache belongs to one model and prompt; a different one must start its own."""
        mine = self.signaler.fingerprint()
        recorded = self.cache.get("fingerprint")
        if recorded is None:
            self.cache.set("fingerprint", mine)
        elif recorded != mine:
            raise ValueError(f"the cache was made with {recorded}, not {mine}")

    def __call__(self, now_ms: int, market: HistoricalOKX, positions: dict[str, Position]) -> list[Signal]:
        self.market.at(now_ms)
        self.clock = datetime.fromtimestamp(now_ms / 1000, UTC)
        cached = self._cached(now_ms)
        todo = [coin for coin in self.watchlist if coin.research not in cached]
        if todo and self.budget is not None and self.stats.spent >= self.budget:
            raise BudgetExhausted(f"spent {self.stats.spent:.2f} USD of the {self.budget:.2f} budget")
        signals = [Signal(now_ms, coin, s, c) for coin, (s, c) in cached.items()]
        self.stats.cached += len(cached)
        if todo:
            results = self._ask(todo, now_ms, positions)
            for coin, result in zip(todo, results, strict=True):
                if result.signal is None:
                    self.stats.failures += 1
                    self.stats.errors.append(f"{self.clock:%m-%d %H:%M} {coin.research}: {result.error}")
                # A failed call that cost nothing (no history, no model) is not cached, so
                # the hour is tried again once the cause is fixed.
                if result.signal is not None or result.tokens_in:
                    self.cache.record_signal(now_ms, coin.research, result)
                signals.append(Signal(now_ms, coin.research, result.signal, result.conviction))
        self.stats.hours += 1
        made = [s for s in signals if s.signal is not None]
        self.empty_hours = 0 if made else self.empty_hours + 1
        self.log(
            f"{self.clock:%Y-%m-%d %H:%M} "
            + " ".join(f"{s.coin.split('-')[0]}={s.signal or '-'}{s.conviction or ''}" for s in signals)
            + f"  calls {self.stats.calls} spent {self.stats.spent:.2f}"
        )
        if self.empty_hours >= MAX_EMPTY_HOURS:
            raise NothingWorks("; ".join(self.stats.errors[-MAX_EMPTY_HOURS * len(self.watchlist):]))
        return signals

    def _ask(self, coins: list[Coin], now_ms: int, positions: dict[str, Position]) -> list[SignalResult]:
        """One answer per coin, the coins asked at once. A call that failed without
        costing anything (the model unreachable or overloaded) is asked again after a
        pause, RETRIES times, before the hour counts as empty."""
        answers: dict[str, SignalResult] = {}
        pending, pause = list(coins), RETRY_PAUSE
        for attempt in range(RETRIES + 1):
            with ThreadPoolExecutor(self.workers) as pool:
                results = list(pool.map(
                    lambda coin: self.signaler.run(coin, now_ms, positions.get(coin.swap)), pending
                ))
            for coin, result in zip(pending, results, strict=True):
                self.stats.calls += 1
                self.stats.spent += result.cost_usd or 0.0
                answers[coin.research] = result
            pending = [c for c in pending if answers[c.research].signal is None and not answers[c.research].tokens_in]
            if not pending or attempt == RETRIES:
                break
            self.log(f"{self.clock:%Y-%m-%d %H:%M} {len(pending)} call(s) failed for nothing"
                     f" ({answers[pending[0].research].error}); retrying in {pause:.0f}s")
            self.sleep(pause)
            pause *= 2
        return [answers[c.research] for c in coins]

    def _cached(self, now_ms: int) -> dict[str, tuple[str | None, int | None]]:
        rows = self.cache.db.execute(
            "SELECT coin, signal, conviction FROM signals WHERE ts = ? ORDER BY id", (now_ms,)
        ).fetchall()
        return {coin: (signal, conviction) for coin, signal, conviction in rows}


def rerun(
    store: HistoryStore, cache: Ledger, signaler: Signaler, market: HistoricalOKX,
    start_ms: int, end_ms: int, *, budget_usd: float | None = None,
    watchlist: tuple[Coin, ...] = WATCHLIST, workers: int = 3, capital: float = 10_000.0,
    params: Params = DEFAULT_PARAMS, log=None, sleep: Callable[[float], None] = time.sleep,
) -> tuple[Result | None, Stats, str | None]:
    """Rerun the signal from ``start_ms`` to ``end_ms`` with the engine in the loop.

    Returns the replay's result (None when the run stopped early), the run's stats,
    and why it stopped early (None when it did not)."""
    maker = Rerun(
        signaler, market, cache, watchlist=watchlist, budget_usd=budget_usd, workers=workers, log=log,
        sleep=sleep,
    )
    try:
        result = replay(
            store, [], start_ms, end_ms, params=params, watchlist=watchlist, capital=capital,
            market=market, signaler=maker,
        )
    except (BudgetExhausted, NothingWorks) as stop:
        return None, maker.stats, f"{type(stop).__name__}: {stop}"
    return result, maker.stats, None


def cache_summary(cache: Ledger) -> dict:
    """What the cache holds: hours, signals, failures, cost, span."""
    row = cache.db.execute(
        "SELECT COUNT(DISTINCT ts), COUNT(*), SUM(signal IS NULL), COALESCE(SUM(cost_usd), 0),"
        " MIN(ts), MAX(ts) FROM signals"
    ).fetchone()
    hours, signals, failures, cost, first, last = row
    return {
        "fingerprint": cache.get("fingerprint"), "hours": hours, "signals": signals, "failures": failures or 0, "cost_usd": cost,
        "first": first, "last": last,
    }
