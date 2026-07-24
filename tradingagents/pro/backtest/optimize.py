"""Parameter optimization (roadmap P2 / architecture track T3).

Searches a strategy's declared ``ParamSpace`` (grid or random), runs one
child backtest per trial, and — crucially — attaches the overfitting guards
(validation.py) to the result: the selected "best" always ships with a
deflated Sharpe and a PBO, so a configuration that only looks good because it
was the best of many trials is visibly flagged, not silently promoted (the
differentiator from docs/research/12_validation_methodology.md).

The driver is decoupled from the engine: it takes a ``backtest_fn`` that maps
a resolved parameter dict to ``(objective_value, per_period_returns)``. The
dashboard job supplies one that runs a real ``BacktestEngine``; tests supply
a synthetic one. ``engine_backtest_fn`` is the standard adapter.

Trials are independent and pure, so ``max_workers`` > 1 fans them across a
``ProcessPoolExecutor`` (docs/research/11_performance_recommendations.md R1)
— the result stays deterministic (trials are reassembled in submission order
before selection, so it matches the serial path byte-for-byte).
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from tradingagents.pro.backtest.strategy import ParamSpace
from tradingagents.pro.backtest.validation import (
    deflated_sharpe_from_returns,
    probability_of_backtest_overfitting,
)

# (objective_value, per-period returns) for one parameter set
BacktestFn = Callable[[dict], "tuple[float, list[float]]"]


@dataclass
class Trial:
    params: dict
    objective: float


@dataclass
class OptResult:
    trials: list[Trial]
    best_params: dict
    best_objective: float
    n_trials: int
    objective_name: str
    search: str
    # guards over the selected best (None when too few trials or the child
    # runs produced unequal-length / empty return series)
    deflated_sharpe: float | None = None
    pbo: float | None = None
    guard_note: str = field(default="")

    def verdict(self) -> str:
        """Plain-language read of the guards for the UI / reports."""
        if self.deflated_sharpe is None or self.pbo is None:
            return "guards unavailable (need >= 2 comparable trials)"
        if self.pbo > 0.5 or self.deflated_sharpe < 0.6:
            return ("no evidence of out-of-sample edge — do not deploy "
                    f"(PBO {self.pbo:.2f}, deflated Sharpe {self.deflated_sharpe:.2f}, "
                    f"{self.n_trials} trials)")
        return (f"survives the overfitting gauntlet (PBO {self.pbo:.2f}, "
                f"deflated Sharpe {self.deflated_sharpe:.2f}, {self.n_trials} trials)")


def _param_sets(space: ParamSpace, search: str, n_trials: int | None,
                seed: int) -> list[dict]:
    if search == "grid":
        return list(space.grid())
    if search == "random":
        if not n_trials or n_trials < 1:
            raise ValueError("random search requires n_trials >= 1")
        rng = random.Random(seed)
        return [space.sample(rng) for _ in range(n_trials)]
    raise ValueError(f"unknown search {search!r} (grid | random)")


def run_optimization(
    space: ParamSpace,
    backtest_fn: BacktestFn,
    *,
    search: str = "grid",
    n_trials: int | None = None,
    seed: int = 0,
    objective_name: str = "sharpe",
    compute_guards: bool = True,
    on_trial: Callable[[int, int, float], None] | None = None,
    cancel: Callable[[], bool] | None = None,
    max_workers: int | None = None,
    search_config: dict | None = None,
) -> OptResult:
    """Run the search and return the ranked trials + the selected best with its
    overfitting guards. ``backtest_fn(params)`` returns
    ``(objective_value, per_period_returns)``; higher objective is better.
    ``on_trial(done, total, best_so_far)`` streams progress; ``cancel()``
    returning True stops the sweep early (the partial is still scored).

    ``max_workers`` > 1 runs trials on a ``ProcessPoolExecutor`` (roadmap R1:
    trials are embarrassingly parallel, and separate processes sidestep the
    GIL). The result is identical to the serial path regardless of completion
    order — trials are re-sorted into submission order before selection — so
    determinism is preserved. ``backtest_fn`` MUST be picklable for the pool
    (use ``EngineTrial``, not the ``engine_backtest_fn`` closure). ``None`` /
    ``1`` keeps the exact serial behaviour.

    ``search="genetic"|"bayesian"`` runs an iterative ask/tell sampler
    (search.py) instead of a static set; ``search_config`` tunes it
    (population/generations, or n_trials/n_startup/batch). Every evaluated
    trial still flows through ``_finalize``, so the guards reflect the FULL
    amount of searching (not just the surviving population)."""
    if search in ("genetic", "bayesian"):
        from tradingagents.pro.backtest.search import build_sampler

        sampler, total_hint = build_sampler(
            space, search, seed, search_config or {})
        trials, returns_by_trial = _run_iterative(
            sampler, backtest_fn, on_trial=on_trial, cancel=cancel,
            max_workers=max_workers, total_hint=total_hint)
        if not trials:
            raise ValueError("no trials completed")
        return _finalize(trials, returns_by_trial, objective_name=objective_name,
                         search=search, compute_guards=compute_guards)

    param_sets = _param_sets(space, search, n_trials, seed)
    if not param_sets:
        raise ValueError("parameter space produced no trials")

    if max_workers and max_workers > 1 and len(param_sets) > 1:
        trials, returns_by_trial = _run_parallel(
            param_sets, backtest_fn, max_workers, on_trial, cancel)
    else:
        trials, returns_by_trial = _run_serial(
            param_sets, backtest_fn, on_trial, cancel)
    if not trials:
        raise ValueError("no trials completed")

    return _finalize(trials, returns_by_trial, objective_name=objective_name,
                     search=search, compute_guards=compute_guards)


def _run_serial(param_sets, backtest_fn, on_trial, cancel):
    trials: list[Trial] = []
    returns_by_trial: list[list[float]] = []
    total = len(param_sets)
    for n, params in enumerate(param_sets, 1):
        if cancel is not None and cancel():
            break
        objective, returns = backtest_fn(params)
        trials.append(Trial(params=params, objective=float(objective)))
        returns_by_trial.append(list(returns))
        if on_trial is not None:
            on_trial(n, total, max(t.objective for t in trials))
    return trials, returns_by_trial


def _run_parallel(param_sets, backtest_fn, max_workers, on_trial, cancel):
    """Fan the trials out over worker processes, then reassemble in submission
    order so best-selection + guards are byte-identical to the serial path."""
    from concurrent.futures import ProcessPoolExecutor, as_completed

    total = len(param_sets)
    results: list[tuple[float, list[float]] | None] = [None] * total
    done = best = 0
    best_seen = False
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(backtest_fn, p): i for i, p in enumerate(param_sets)}
        for fut in as_completed(futures):
            idx = futures[fut]
            objective, returns = fut.result()
            results[idx] = (float(objective), list(returns))
            done += 1
            best = float(objective) if not best_seen else max(best, float(objective))
            best_seen = True
            if on_trial is not None:
                on_trial(done, total, best)
            if cancel is not None and cancel():
                for other in futures:  # cancel only not-yet-started trials
                    other.cancel()
                break
    trials: list[Trial] = []
    returns_by_trial: list[list[float]] = []
    for i in range(total):  # submission order; drop trials cancelled before start
        if results[i] is None:
            continue
        objective, returns = results[i]
        trials.append(Trial(params=param_sets[i], objective=objective))
        returns_by_trial.append(returns)
    return trials, returns_by_trial


def _run_iterative(sampler, backtest_fn, *, on_trial, cancel, max_workers,
                   total_hint):
    """Drive an ask/tell sampler: evaluate each generation/batch through the
    same serial/parallel helpers (reassembled in submission order), then
    ``tell`` the sampler the results in that order so its RNG advances
    deterministically regardless of worker completion order. Accumulates EVERY
    evaluated trial (not just the final population) for the guards."""
    trials: list[Trial] = []
    returns_by_trial: list[list[float]] = []
    while True:
        if cancel is not None and cancel():
            break
        batch = sampler.ask()
        if not batch:
            break
        # evaluate the whole batch (no per-item cancel: batches are small, and
        # a mid-batch cut would desync the sampler's trial counter)
        if max_workers and max_workers > 1 and len(batch) > 1:
            batch_trials, batch_returns = _run_parallel(
                batch, backtest_fn, max_workers, None, None)
        else:
            batch_trials, batch_returns = _run_serial(
                batch, backtest_fn, None, None)
        sampler.tell([t.params for t in batch_trials],
                     [t.objective for t in batch_trials])
        trials.extend(batch_trials)
        returns_by_trial.extend(batch_returns)
        if on_trial is not None:
            on_trial(len(trials), max(total_hint, len(trials)),
                     max(t.objective for t in trials))
    return trials, returns_by_trial


def _finalize(trials, returns_by_trial, *, objective_name, search, compute_guards):
    best_idx = max(range(len(trials)), key=lambda i: trials[i].objective)
    dsr = pbo = None
    note = ""
    if not compute_guards:
        note = "guards disabled"
    elif len(trials) < 2:
        note = "single trial — no selection to deflate"
    else:
        lengths = {len(r) for r in returns_by_trial}
        if lengths == {0}:
            note = "no returns produced — guards skipped"
        elif len(lengths) != 1:
            note = "unequal-length return series — guards skipped"
        else:
            dsr = deflated_sharpe_from_returns(returns_by_trial, best_idx)
            pbo = probability_of_backtest_overfitting(returns_by_trial)

    return OptResult(
        trials=trials,
        best_params=trials[best_idx].params,
        best_objective=trials[best_idx].objective,
        n_trials=len(trials),
        objective_name=objective_name,
        search=search,
        deflated_sharpe=dsr,
        pbo=pbo,
        guard_note=note,
    )


def engine_backtest_fn(
    strategy_id: str,
    config,
    replay_factory: Callable[[], object],
    *,
    min_history: int = 60,
    periods_per_year: int = 252,
    initial_equity: float = 100_000.0,
    objective_name: str = "sharpe",
) -> BacktestFn:
    """Standard adapter: each call builds a FRESH strategy (from params),
    replay (from ``replay_factory`` — replays are stateful, never reused), and
    broker, runs one ``BacktestEngine``, and returns
    ``(report.<objective>, per-bar equity returns)``."""

    def fn(params: dict) -> tuple[float, list[float]]:
        from tradingagents.pro.backtest import build_strategy
        from tradingagents.pro.backtest.broker import SimBroker
        from tradingagents.pro.backtest.engine import BacktestEngine
        from tradingagents.pro.backtest.metrics import equity_returns

        engine = BacktestEngine(
            None, config, replay_factory(),
            broker=SimBroker(initial_equity=initial_equity),
            memory=None, min_history=min_history, decide_every=1,
            periods_per_year=periods_per_year,
            strategy=build_strategy(strategy_id, params))
        result = engine.run()
        objective = getattr(result.report, objective_name, None)
        return float(objective or 0.0), equity_returns(result.equity_curve)

    return fn


@dataclass
class EngineTrial:
    """Picklable equivalent of ``engine_backtest_fn`` for the process pool.

    The closure adapter captures a ``replay_factory`` lambda (unpicklable);
    this holds the raw replay ingredients instead and rebuilds a fresh
    ``BarReplay`` on every call, so an instance ships cleanly to a worker
    process. Behaviour is identical to ``engine_backtest_fn`` (same fresh
    strategy/replay/broker per trial, same objective + returns)."""

    strategy_id: str
    config: object
    symbol: str
    asset: object
    bars: list
    min_history: int = 60
    periods_per_year: int = 252
    initial_equity: float = 100_000.0
    objective_name: str = "sharpe"

    def __call__(self, params: dict) -> tuple[float, list[float]]:
        from tradingagents.pro.backtest import build_strategy
        from tradingagents.pro.backtest.broker import SimBroker
        from tradingagents.pro.backtest.data import BarReplay
        from tradingagents.pro.backtest.engine import BacktestEngine
        from tradingagents.pro.backtest.metrics import equity_returns

        replay = BarReplay(self.symbol, self.asset, self.bars,
                           window=self.min_history, precompute_indicators=True)
        engine = BacktestEngine(
            None, self.config, replay,
            broker=SimBroker(initial_equity=self.initial_equity),
            memory=None, min_history=self.min_history, decide_every=1,
            periods_per_year=self.periods_per_year,
            strategy=build_strategy(self.strategy_id, params))
        result = engine.run()
        objective = getattr(result.report, self.objective_name, None)
        return float(objective or 0.0), equity_returns(result.equity_curve)


def objective_choices() -> Iterable[str]:
    """Report metrics on the base PerformanceReport that make sensible
    optimization objectives (higher is better) — for the API/UI select."""
    return ("sharpe", "sortino", "total_return", "profit_factor",
            "expectancy_r")


__all__ = [
    "BacktestFn",
    "EngineTrial",
    "OptResult",
    "Trial",
    "engine_backtest_fn",
    "objective_choices",
    "run_optimization",
]
