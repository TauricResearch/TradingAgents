"""Walk-forward evaluation over rolling windows.

The Pro pipeline has no fitted parameters yet (LLM reasoning + fixed
rules), so "optimization" here honestly means *stability evaluation*: run
each out-of-sample window independently and report the dispersion of
results. When Phase 8 adds tunable policy parameters, the train ranges
become their fitting data — the windowing is already correct for that.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import mean

from tradingagents.contracts import OHLCVBar
from tradingagents.pro.backtest.engine import BacktestResult
from tradingagents.pro.backtest.optimize import BacktestFn, run_optimization
from tradingagents.pro.backtest.strategy import ParamSpace


@dataclass(frozen=True)
class Window:
    train_start: int
    train_end: int  # exclusive; also test_start
    test_end: int  # exclusive


def walk_forward_windows(n_bars: int, train: int, test: int, step: int | None = None
                         ) -> list[Window]:
    """Rolling train/test index windows over ``n_bars``."""
    if train < 1 or test < 1:
        raise ValueError("train and test must be >= 1")
    step = step or test
    if step < 1:
        raise ValueError("step must be >= 1")
    windows = []
    start = 0
    while start + train + test <= n_bars:
        windows.append(Window(start, start + train, start + train + test))
        start += step
    return windows


@dataclass
class WalkForwardResult:
    windows: list[Window]
    results: list[BacktestResult]

    def summary(self) -> dict:
        if not self.results:
            return {"windows": 0}
        returns = [r.report.total_return for r in self.results]
        sharpes = [r.report.sharpe for r in self.results]
        return {
            "windows": len(self.results),
            "mean_return": mean(returns),
            "worst_return": min(returns),
            "best_return": max(returns),
            "mean_sharpe": mean(sharpes),
            "profitable_windows": sum(1 for r in returns if r > 0),
            "total_trades": sum(r.report.n_trades for r in self.results),
        }


def run_walk_forward(
    engine_factory: Callable[[Sequence[OHLCVBar], Window], BacktestResult],
    bars: Sequence[OHLCVBar],
    train: int,
    test: int,
    step: int | None = None,
) -> WalkForwardResult:
    """Evaluate each test window out-of-sample.

    ``engine_factory(window_bars, window)`` receives the train+test slice
    (train bars are warm-up history; decisions score only in the test
    range) and returns that window's BacktestResult.
    """
    windows = walk_forward_windows(len(bars), train, test, step)
    results = [
        engine_factory(bars[w.train_start : w.test_end], w) for w in windows
    ]
    return WalkForwardResult(windows=windows, results=results)


# --- walk-forward *fitting* (roadmap P2.2 / track T3) -------------------------


@dataclass(frozen=True)
class WFWindow:
    """A fit/score window. ``embargo`` bars are dropped between the train and
    test ranges so serial correlation across the boundary can't leak a fitted
    parameter's edge into its own out-of-sample score."""

    train_start: int
    train_end: int  # exclusive
    test_start: int  # == train_end + embargo
    test_end: int  # exclusive


def walk_forward_opt_windows(
    n_bars: int, train: int, test: int, step: int | None = None, embargo: int = 0,
) -> list[WFWindow]:
    if train < 1 or test < 1:
        raise ValueError("train and test must be >= 1")
    if embargo < 0:
        raise ValueError("embargo must be >= 0")
    step = step or test
    if step < 1:
        raise ValueError("step must be >= 1")
    windows: list[WFWindow] = []
    start = 0
    while start + train + embargo + test <= n_bars:
        train_end = start + train
        test_start = train_end + embargo
        windows.append(WFWindow(start, train_end, test_start, test_start + test))
        start += step
    return windows


@dataclass
class WalkForwardOptResult:
    """Result of fitting params on each train window and scoring the chosen
    params on the immediately-following (embargoed) test window. The headline
    is the OUT-OF-SAMPLE, concatenated-across-windows performance — never the
    in-sample fit."""

    windows: list[WFWindow]
    chosen_params: list[dict]
    oos_objective: list[float]
    oos_returns: list[list[float]]
    objective_name: str

    def _concatenated(self) -> list[float]:
        return [r for window in self.oos_returns for r in window]

    def summary(self) -> dict:
        if not self.windows:
            return {"windows": 0}
        rets = self._concatenated()
        mean_r = mean(rets) if rets else 0.0
        std = (math.sqrt(sum((r - mean_r) ** 2 for r in rets) / len(rets))
               if len(rets) > 1 else 0.0)
        params_seen = Counter(tuple(sorted(p.items())) for p in self.chosen_params)
        best_common, best_count = params_seen.most_common(1)[0]
        return {
            "windows": len(self.windows),
            "objective": self.objective_name,
            "mean_oos_objective": mean(self.oos_objective) if self.oos_objective else 0.0,
            "worst_oos_objective": min(self.oos_objective) if self.oos_objective else 0.0,
            "profitable_windows": sum(1 for o in self.oos_objective if o > 0),
            "oos_sharpe": (mean_r / std) if std > 0 else 0.0,  # per-period units
            # parameter stability: fewer distinct sets chosen = steadier fit
            "distinct_param_sets": len(params_seen),
            "most_common_params": dict(best_common),
            "most_common_share": best_count / len(self.chosen_params),
        }


def run_walk_forward_optimization(
    space: ParamSpace,
    bars: Sequence[OHLCVBar],
    backtest_fn_factory: Callable[[Sequence[OHLCVBar]], BacktestFn],
    *,
    train: int,
    test: int,
    step: int | None = None,
    embargo: int = 0,
    search: str = "grid",
    n_trials: int | None = None,
    seed: int = 0,
    objective_name: str = "sharpe",
) -> WalkForwardOptResult:
    """Fit on each train window, score the chosen params OOS on the next test
    window. ``backtest_fn_factory(bar_slice)`` returns a ``backtest_fn`` bound
    to that slice (so fitting and scoring run on disjoint, embargoed data).
    Windows must be sized above the strategy's warm-up or a slice yields no
    decisions."""
    windows = walk_forward_opt_windows(len(bars), train, test, step, embargo)
    chosen: list[dict] = []
    oos_objective: list[float] = []
    oos_returns: list[list[float]] = []
    for w in windows:
        train_fn = backtest_fn_factory(bars[w.train_start : w.train_end])
        fit = run_optimization(
            space, train_fn, search=search, n_trials=n_trials, seed=seed,
            objective_name=objective_name, compute_guards=False)
        test_fn = backtest_fn_factory(bars[w.test_start : w.test_end])
        objective, returns = test_fn(fit.best_params)
        chosen.append(fit.best_params)
        oos_objective.append(float(objective))
        oos_returns.append(list(returns))
    return WalkForwardOptResult(
        windows=windows, chosen_params=chosen, oos_objective=oos_objective,
        oos_returns=oos_returns, objective_name=objective_name)
