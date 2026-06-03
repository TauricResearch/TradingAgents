"""Pure forward-test math — signal → position → return series → aggregate metrics.

Resolution-agnostic. Callers pass a ``Bars`` with N close prices; this module
produces an N-1-length return series and reduces it to scalar metrics.
"""

from __future__ import annotations

import math
import statistics
from typing import List

from tradingagents.backtest.prices import Bars, Resolution


_DECISION_TO_POSITION = {"BUY": 1, "HOLD": 0, "SELL": -1}


def position_from_decision(decision: str) -> int:
    """Map BUY/HOLD/SELL → +1/0/-1. Raises ValueError on unknown."""
    key = decision.strip().upper()
    if key not in _DECISION_TO_POSITION:
        raise ValueError(
            f"Unknown decision {decision!r}; expected BUY / HOLD / SELL"
        )
    return _DECISION_TO_POSITION[key]


def compute_returns(bars: Bars, *, position: int) -> List[float]:
    """Signal-adjusted bar-over-bar return series.

    For N bars returns a list of length N-1. Each element is
    ``position * (close[i+1] - close[i]) / close[i]``. When ``position == 0``
    the series is all zeros (flat).
    """
    if len(bars.bars) < 2:
        return []
    out: List[float] = []
    for (_, prev_close), (_, this_close) in zip(bars.bars, bars.bars[1:]):
        raw = (this_close - prev_close) / prev_close
        out.append(position * raw)
    return out


def total_return(*, entry: float, exit: float, position: int) -> float:
    """Signal-adjusted total return over the window."""
    if entry <= 0:
        raise ValueError(f"entry price must be positive; got {entry}")
    return position * (exit - entry) / entry


_ANNUALIZATION = {
    Resolution.DAILY: math.sqrt(252),
    Resolution.ONE_MIN: math.sqrt(252 * 390),  # ~390 1-min bars per US session
}


def sharpe_ratio(returns: List[float], *, resolution: Resolution) -> float:
    """Annualised Sharpe (zero risk-free rate). Returns 0 for degenerate inputs."""
    if len(returns) < 2:
        return 0.0
    mean = statistics.fmean(returns)
    try:
        std = statistics.stdev(returns)
    except statistics.StatisticsError:
        return 0.0
    if std == 0:
        return 0.0
    return (mean / std) * _ANNUALIZATION[resolution]


def max_drawdown(returns: List[float]) -> float:
    """Largest peak-to-trough decline in the cumulative-return curve.

    Returns a non-positive value. ``0.0`` means no drawdown.
    """
    if not returns:
        return 0.0
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for r in returns:
        equity *= 1.0 + r
        if equity > peak:
            peak = equity
        dd = equity / peak - 1.0
        if dd < worst:
            worst = dd
    return worst


def win_rate(returns: List[float]) -> float:
    """Fraction of bar-returns strictly greater than zero."""
    if not returns:
        return 0.0
    wins = sum(1 for r in returns if r > 0)
    return wins / len(returns)
