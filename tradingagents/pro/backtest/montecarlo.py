"""Monte Carlo robustness analysis by trade-sequence bootstrap.

Resamples the realized per-trade P&L sequence (with replacement) to ask:
how much of the backtest's outcome is path luck? Deterministic under a
seed. Operates on trade P&L, not bar returns, so costs and sizing effects
stay embedded in the resampled units.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import quantiles


@dataclass(frozen=True)
class MonteCarloSummary:
    n_paths: int
    final_equity_p5: float
    final_equity_p50: float
    final_equity_p95: float
    max_drawdown_p50: float
    max_drawdown_p95: float
    prob_loss: float  # fraction of paths ending below initial equity


def bootstrap_paths(
    trade_pnls: Sequence[float],
    initial_equity: float,
    n_paths: int = 1000,
    seed: int = 7,
) -> list[list[float]]:
    if len(trade_pnls) < 2:
        raise ValueError("need at least 2 trades to bootstrap")
    if initial_equity <= 0 or n_paths < 1:
        raise ValueError("initial_equity must be > 0 and n_paths >= 1")
    rng = random.Random(seed)
    paths = []
    for _ in range(n_paths):
        equity = initial_equity
        path = [equity]
        for _ in range(len(trade_pnls)):
            equity += rng.choice(trade_pnls)
            path.append(equity)
        paths.append(path)
    return paths


def _path_max_drawdown(path: Sequence[float]) -> float:
    peak, worst = float("-inf"), 0.0
    for value in path:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def monte_carlo_summary(
    trade_pnls: Sequence[float],
    initial_equity: float,
    n_paths: int = 1000,
    seed: int = 7,
) -> MonteCarloSummary:
    paths = bootstrap_paths(trade_pnls, initial_equity, n_paths, seed)
    finals = sorted(path[-1] for path in paths)
    drawdowns = sorted(_path_max_drawdown(path) for path in paths)

    def pct(sorted_values: list[float], q: float) -> float:
        if len(sorted_values) == 1:
            return sorted_values[0]
        cuts = quantiles(sorted_values, n=100, method="inclusive")
        return cuts[max(0, min(98, round(q * 100) - 1))]

    return MonteCarloSummary(
        n_paths=n_paths,
        final_equity_p5=pct(finals, 0.05),
        final_equity_p50=pct(finals, 0.50),
        final_equity_p95=pct(finals, 0.95),
        max_drawdown_p50=pct(drawdowns, 0.50),
        max_drawdown_p95=pct(drawdowns, 0.95),
        prob_loss=sum(1 for f in finals if f < initial_equity) / len(finals),
    )
