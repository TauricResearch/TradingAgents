"""Walk-forward evaluation over rolling windows.

The Pro pipeline has no fitted parameters yet (LLM reasoning + fixed
rules), so "optimization" here honestly means *stability evaluation*: run
each out-of-sample window independently and report the dispersion of
results. When Phase 8 adds tunable policy parameters, the train ranges
become their fitting data — the windowing is already correct for that.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import mean

from tradingagents.contracts import OHLCVBar
from tradingagents.pro.backtest.engine import BacktestResult


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
