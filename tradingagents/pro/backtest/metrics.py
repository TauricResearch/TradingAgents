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
    # R accounting (risk unit = qty × |entry − initial stop| per trade)
    avg_r: float = 0.0            # mean realized R-multiple
    avg_planned_rr: float = 0.0   # mean ticket R:R (ladder geometry)
    expectancy_r: float = 0.0     # mean realized R — the headline edge number
    win_rate_ex_scratch: float = 0.0  # wins / decided trades (|R| > scratch band)
    scratches: int = 0            # breakeven-band exits (|R| <= 0.1)
    exit_reasons: dict = None     # reason -> count

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
    # R accounting: scratches (|R| inside the breakeven band, e.g. a stop
    # moved to breakeven after TP1's partial) are neither wins nor losses —
    # counting them as losses would misstate the strategy's hit rate.
    # getattr: callers reconstruct trade-like objects (journal views) that
    # may predate the R fields
    r_values = [r for t in trades
                if (r := getattr(t, "r_multiple", None)) is not None]
    scratch_band = 0.1
    decided = [r for r in r_values if abs(r) > scratch_band]
    decided_wins = sum(1 for r in decided if r > 0)
    planned = [p for t in trades
               if (p := getattr(t, "planned_rr", None)) is not None]
    reasons: dict[str, int] = {}
    for t in trades:
        reason = getattr(t, "reason", "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1
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
        avg_r=statistics.mean(r_values) if r_values else 0.0,
        avg_planned_rr=statistics.mean(planned) if planned else 0.0,
        expectancy_r=statistics.mean(r_values) if r_values else 0.0,
        win_rate_ex_scratch=(decided_wins / len(decided)) if decided else 0.0,
        scratches=len(r_values) - len(decided),
        exit_reasons=reasons,
    )
