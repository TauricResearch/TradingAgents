from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .models import BacktestResult, DIRECTION_MAP

logger = logging.getLogger(__name__)


def business_days_between(start_date: str, end_date: str) -> int:
    """Count business days between two ISO-8601 date strings (exclusive of end)."""
    return int(np.busday_count(start_date, end_date))


def get_holding_days(
    current_date: str,
    next_signal_date: Optional[str],
    hold_days_override: Optional[int],
    max_fallback_days: int = 21,
) -> int:
    """Return the number of trading days to hold a signal for return measurement."""
    if hold_days_override is not None:
        return hold_days_override
    if next_signal_date is not None:
        return max(1, business_days_between(current_date, next_signal_date))
    return max_fallback_days


def is_win(direction: int, raw_return: float) -> Optional[bool]:
    """Return True if direction matched return sign, None for HOLD or tie."""
    if direction == 0:
        return None
    if raw_return == 0.0:
        return None
    return (direction > 0) == (raw_return > 0)


from tradingagents.backtesting.returns import fetch_returns


@dataclass
class BacktestSummary:
    # Always check signal_counts first — a backtest with 40 HOLDs and 2 Buys
    # produces a meaningless win rate.
    signal_counts: dict          # {"Buy": 3, "Hold": 8, ...}
    error_count: int             # pipeline failures + unresolvable return fetches
    hold_count: int              # HOLD signals (excluded from directional win rate)

    # Raw returns (direction-neutral — raw asset move, not strategy P&L)
    total_return: Optional[float]
    mean_return: Optional[float]
    cumulative_equity: list      # strategy equity curve starting at 1.0

    # Alpha
    mean_alpha: Optional[float]
    pct_beat_spy: Optional[float]

    # Signal quality
    win_rate: Optional[float]            # directional accuracy; excludes HOLD and ties
    precision_recall_per_tier: dict      # per-tier {"count": N, "win_rate": float|None}

    # Risk (annualised using periods_per_year)
    sharpe_ratio: Optional[float]
    max_drawdown: Optional[float]        # <= 0.0; peak-to-trough as fraction of peak
    volatility: Optional[float]


class BacktestReport:
    def __init__(
        self,
        results: list[BacktestResult],
        risk_free_rate: float = 0.0,
        periods_per_year: int = 12,
    ) -> None:
        self.results = results
        self.risk_free_rate = risk_free_rate
        self.periods_per_year = periods_per_year

    def compute(self, hold_days_override: Optional[int] = None) -> BacktestSummary:
        from collections import Counter

        signal_counts = dict(
            Counter(r.rating for r in self.results if r.error is None and r.rating)
        )
        error_count = sum(1 for r in self.results if r.error is not None)

        # Sort valid results by (ticker, trade_date) for holding period calculation
        valid = sorted(
            [r for r in self.results if r.error is None],
            key=lambda r: (r.ticker, r.trade_date),
        )

        # Resolve forward returns for each valid result
        from itertools import groupby as _groupby

        resolved = []  # list of (result, raw_return, alpha)
        for _ticker, group in _groupby(valid, key=lambda r: r.ticker):
            ticker_results = list(group)
            for i, result in enumerate(ticker_results):
                next_date = (
                    ticker_results[i + 1].trade_date
                    if i + 1 < len(ticker_results)
                    else None
                )
                holding = get_holding_days(result.trade_date, next_date, hold_days_override)
                raw, alpha, _days = fetch_returns(result.ticker, result.trade_date, holding)
                if raw is None:
                    error_count += 1
                else:
                    resolved.append((result, raw, alpha))

        hold_count = signal_counts.get("Hold", 0)

        if not resolved:
            return BacktestSummary(
                signal_counts=signal_counts, error_count=error_count, hold_count=hold_count,
                total_return=None, mean_return=None, cumulative_equity=[1.0],
                mean_alpha=None, pct_beat_spy=None,
                win_rate=None, precision_recall_per_tier={},
                sharpe_ratio=None, max_drawdown=None, volatility=None,
            )

        returns = [raw for _, raw, _ in resolved]
        alphas = [a for _, _, a in resolved]

        # Equity curve — direction-adjusted P&L
        equity = [1.0]
        for result, raw, _ in resolved:
            d = result.direction or 0
            equity.append(equity[-1] * (1 + d * raw))

        # Win rate (excludes HOLD and ties)
        decisive = [
            is_win(result.direction, raw)
            for result, raw, _ in resolved
            if result.direction is not None
        ]
        decisive_bools = [w for w in decisive if w is not None]
        win_rate = (
            sum(decisive_bools) / len(decisive_bools) if decisive_bools else None
        )

        # Per-tier stats
        tier_stats: dict = {}
        for rating in ["Buy", "Overweight", "Hold", "Underweight", "Sell"]:
            tier = [(r, raw, a) for r, raw, a in resolved if r.rating == rating]
            if not tier:
                continue
            if rating == "Hold":
                tier_stats[rating] = {"count": len(tier)}
                continue
            d = DIRECTION_MAP.get(rating, 0)
            tier_wins = [is_win(d, raw) for _, raw, _ in tier]
            decisive_tier = [w for w in tier_wins if w is not None]
            tier_stats[rating] = {
                "count": len(tier),
                "win_rate": (
                    sum(decisive_tier) / len(decisive_tier) if decisive_tier else None
                ),
            }

        # Risk metrics
        mean_r = sum(returns) / len(returns)
        vol: Optional[float] = None
        sharpe: Optional[float] = None
        if len(returns) > 1:
            variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
            vol = math.sqrt(variance) if variance > 0 else 0.0
            rf_per_period = self.risk_free_rate / self.periods_per_year
            if vol and vol > 0:
                sharpe = (
                    (mean_r - rf_per_period)
                    / vol
                    * math.sqrt(self.periods_per_year)
                )

        # Max drawdown
        peak = equity[0]
        max_dd = 0.0
        for val in equity:
            peak = max(peak, val)
            dd = (peak - val) / peak
            max_dd = max(max_dd, dd)

        return BacktestSummary(
            signal_counts=signal_counts,
            error_count=error_count,
            hold_count=hold_count,
            total_return=sum(returns),
            mean_return=mean_r,
            cumulative_equity=equity,
            mean_alpha=sum(alphas) / len(alphas),
            pct_beat_spy=sum(1 for a in alphas if a > 0) / len(alphas),
            win_rate=win_rate,
            precision_recall_per_tier=tier_stats,
            sharpe_ratio=sharpe,
            max_drawdown=-max_dd,
            volatility=vol,
        )
