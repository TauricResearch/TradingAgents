"""Performance metrics over equity curves and closed trades.

These are the Phase 8 RL objectives (Sharpe, Sortino, profit factor, max
drawdown, win rate, expectancy) — deterministic, unit-tested, and shared
by the backtester, the dashboard, and the reward functions later.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from tradingagents.pro.backtest.broker import ClosedTrade

PERIODS_PER_YEAR = 252  # daily bars; callers scale for other timeframes


@dataclass(frozen=True)
class PerformanceReport:
    total_return: float
    max_drawdown: float
    sharpe: float
    sortino: float
    win_rate: float
    profit_factor: float
    expectancy: float
    n_trades: int

    def as_dict(self) -> dict:
        return asdict(self)


def equity_returns(equity_curve: Sequence[float]) -> list[float]:
    if len(equity_curve) < 2:
        return []
    return [
        (b - a) / a for a, b in zip(equity_curve, equity_curve[1:], strict=False) if a > 0
    ]


def max_drawdown(equity_curve: Sequence[float]) -> float:
    """Largest peak-to-trough decline as a positive fraction."""
    peak, worst = float("-inf"), 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def sharpe_ratio(returns: Sequence[float], periods_per_year: int = PERIODS_PER_YEAR) -> float:
    if len(returns) < 2:
        return 0.0
    stdev = statistics.stdev(returns)
    if stdev == 0:
        return 0.0
    return (statistics.mean(returns) / stdev) * math.sqrt(periods_per_year)


def sortino_ratio(returns: Sequence[float], periods_per_year: int = PERIODS_PER_YEAR) -> float:
    if len(returns) < 2:
        return 0.0
    downside = [r for r in returns if r < 0]
    if not downside:
        return float("inf") if statistics.mean(returns) > 0 else 0.0
    downside_dev = math.sqrt(math.fsum(r * r for r in downside) / len(returns))
    if downside_dev == 0:
        return 0.0
    return (statistics.mean(returns) / downside_dev) * math.sqrt(periods_per_year)


def performance_report(
    equity_curve: Sequence[float],
    trades: Sequence[ClosedTrade],
    periods_per_year: int = PERIODS_PER_YEAR,
) -> PerformanceReport:
    returns = equity_returns(equity_curve)
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = math.fsum(wins)
    gross_loss = -math.fsum(losses)
    total_return = (
        (equity_curve[-1] - equity_curve[0]) / equity_curve[0]
        if len(equity_curve) >= 2 and equity_curve[0] > 0
        else 0.0
    )
    return PerformanceReport(
        total_return=total_return,
        max_drawdown=max_drawdown(equity_curve),
        sharpe=sharpe_ratio(returns, periods_per_year),
        sortino=sortino_ratio(returns, periods_per_year),
        win_rate=len(wins) / len(pnls) if pnls else 0.0,
        profit_factor=gross_win / gross_loss if gross_loss > 0 else (
            float("inf") if gross_win > 0 else 0.0
        ),
        expectancy=statistics.mean(pnls) if pnls else 0.0,
        n_trades=len(pnls),
    )
