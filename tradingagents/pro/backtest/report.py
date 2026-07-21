"""Extended performance analytics for the institutional backtest report.

Builds on ``backtest/metrics.py`` (the canonical Sharpe/Sortino/max-drawdown/
profit-factor/expectancy core) with the metrics an institutional report needs
but the core deliberately omits: CAGR, Calmar, recovery factor, rolling Sharpe,
risk of ruin, win/loss streaks, average/largest win & loss, the underwater
(drawdown) curve, calendar-bucketed returns, and a buy-&-hold benchmark with
alpha/beta.

Everything here is deterministic and unit-testable: pure functions over an
equity curve, a list of ``ClosedTrade``, and (for calendar/benchmark work)
timestamps. No LLM, no I/O, no fabricated inputs — every number traces to the
recorded backtest.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime

from tradingagents.pro.backtest.broker import ClosedTrade
from tradingagents.pro.backtest.metrics import (
    PERIODS_PER_YEAR,
    equity_returns,
    max_drawdown,
    sharpe_ratio,
)
from tradingagents.pro.backtest.montecarlo import bootstrap_paths

# ── time-weighted growth ──────────────────────────────────────────────────


def cagr(equity_curve: Sequence[float], years: float) -> float:
    """Compound annual growth rate. 0.0 when the horizon or capital is
    degenerate (keeps the report finite rather than raising)."""
    if len(equity_curve) < 2 or years <= 0:
        return 0.0
    start, end = equity_curve[0], equity_curve[-1]
    if start <= 0 or end <= 0:
        return 0.0
    return (end / start) ** (1.0 / years) - 1.0


def calmar_ratio(cagr_value: float, max_dd: float) -> float:
    """Annualized return per unit of max drawdown."""
    return cagr_value / max_dd if max_dd > 0 else 0.0


def recovery_factor(net_profit: float, max_dd_abs: float) -> float:
    """Net profit divided by the absolute peak-to-trough loss (currency)."""
    return net_profit / max_dd_abs if max_dd_abs > 0 else 0.0


def rolling_sharpe(
    returns: Sequence[float],
    window: int = 30,
    periods_per_year: int = PERIODS_PER_YEAR,
) -> list[float]:
    """Sharpe over a trailing window, one value per step once the window is
    full. Empty when there are fewer than ``window`` returns."""
    if window < 2 or len(returns) < window:
        return []
    return [
        sharpe_ratio(returns[i - window : i], periods_per_year)
        for i in range(window, len(returns) + 1)
    ]


def drawdown_curve(equity_curve: Sequence[float]) -> list[float]:
    """Underwater series: fractional distance below the running peak at each
    point (0.0 at new highs, positive while underwater)."""
    out: list[float] = []
    peak = float("-inf")
    for value in equity_curve:
        peak = max(peak, value)
        out.append((peak - value) / peak if peak > 0 else 0.0)
    return out


# ── trade-distribution stats ──────────────────────────────────────────────


@dataclass(frozen=True)
class TradeStats:
    avg_win: float
    avg_loss: float  # negative
    largest_win: float
    largest_loss: float  # negative
    max_consecutive_wins: int
    max_consecutive_losses: int

    def as_dict(self) -> dict:
        return asdict(self)


def trade_stats(trades: Sequence[ClosedTrade]) -> TradeStats:
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    max_w = max_l = cur_w = cur_l = 0
    for p in pnls:
        if p > 0:
            cur_w, cur_l = cur_w + 1, 0
        elif p < 0:
            cur_l, cur_w = cur_l + 1, 0
        else:
            cur_w = cur_l = 0
        max_w, max_l = max(max_w, cur_w), max(max_l, cur_l)
    return TradeStats(
        avg_win=statistics.mean(wins) if wins else 0.0,
        avg_loss=statistics.mean(losses) if losses else 0.0,
        largest_win=max(wins) if wins else 0.0,
        largest_loss=min(losses) if losses else 0.0,
        max_consecutive_wins=max_w,
        max_consecutive_losses=max_l,
    )


def risk_of_ruin(
    trade_pnls: Sequence[float],
    initial_equity: float,
    ruin_fraction: float = 0.5,
    n_paths: int = 1000,
    seed: int = 7,
) -> float:
    """Empirical probability that a bootstrapped reordering of the realized
    trade PnLs ever draws the account down to ``ruin_fraction`` of starting
    equity. Data-driven (reuses the Monte-Carlo bootstrap), not a closed-form
    gambler's-ruin approximation — so it honours the actual PnL distribution.
    Returns 0.0 when there are too few trades to bootstrap."""
    if len(trade_pnls) < 2 or initial_equity <= 0:
        return 0.0
    ruin_level = initial_equity * ruin_fraction
    paths = bootstrap_paths(trade_pnls, initial_equity, n_paths=n_paths, seed=seed)
    ruined = sum(1 for path in paths if min(path) <= ruin_level)
    return ruined / len(paths)


# ── benchmark (buy & hold) + alpha/beta ───────────────────────────────────


def buy_hold_curve(
    closes: Sequence[float], initial_equity: float
) -> list[float]:
    """Equity of holding the asset from the first close, normalized to the
    strategy's starting capital — the benchmark for alpha/beta."""
    if not closes or closes[0] <= 0:
        return []
    return [initial_equity * (c / closes[0]) for c in closes]


def alpha_beta(
    strategy_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    periods_per_year: int = PERIODS_PER_YEAR,
) -> tuple[float, float]:
    """OLS of strategy step-returns on benchmark step-returns.
    Returns (annualized_alpha, beta). Beta 0 / alpha 0 when undefined."""
    n = min(len(strategy_returns), len(benchmark_returns))
    if n < 2:
        return 0.0, 0.0
    s = list(strategy_returns[:n])
    b = list(benchmark_returns[:n])
    mean_b = statistics.mean(b)
    var_b = statistics.pvariance(b)
    if var_b == 0:
        return 0.0, 0.0
    mean_s = statistics.mean(s)
    cov = math.fsum((bi - mean_b) * (si - mean_s) for bi, si in zip(b, s, strict=False)) / n
    beta = cov / var_b
    alpha_per_period = mean_s - beta * mean_b
    return alpha_per_period * periods_per_year, beta


# ── calendar-bucketed returns (period % change of equity) ─────────────────


def calendar_returns(
    timestamps: Sequence[datetime], equity_curve: Sequence[float], freq: str
) -> list[tuple[str, float]]:
    """Period returns of the (timestamp, equity) series, bucketed by calendar
    ``freq`` ("D"/"W"/"M"). Each entry is (period_label, fractional_return of
    the period's last equity vs the previous period's last). Uses pandas."""
    import pandas as pd

    n = min(len(timestamps), len(equity_curve))
    if n < 2:
        return []
    ser = pd.Series(
        list(equity_curve[:n]), index=pd.DatetimeIndex(list(timestamps[:n]))
    )
    period_end = ser.resample(freq).last().dropna()
    rets = period_end.pct_change().dropna()
    fmt = "%Y-%m" if freq.startswith("M") else "%Y-%m-%d"
    return [(idx.strftime(fmt), float(v)) for idx, v in rets.items()]


# ── the bundle ────────────────────────────────────────────────────────────


@dataclass
class ExtendedReport:
    """Everything the base ``PerformanceReport`` lacks, computed from the same
    recorded backtest. Serializes flat for the metrics.json artifact."""

    cagr: float
    calmar: float
    recovery_factor: float
    risk_of_ruin: float
    alpha: float
    beta: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    benchmark_total_return: float
    # series (kept out of the flat scalar view; emitted to their own CSVs)
    drawdown_curve: list[float] = field(default_factory=list, repr=False)
    rolling_sharpe: list[float] = field(default_factory=list, repr=False)
    monthly_returns: list[tuple[str, float]] = field(default_factory=list, repr=False)
    weekly_returns: list[tuple[str, float]] = field(default_factory=list, repr=False)
    daily_returns: list[tuple[str, float]] = field(default_factory=list, repr=False)

    def scalar_dict(self) -> dict:
        """Flat scalar metrics only (for JSON/markdown tables)."""
        d = asdict(self)
        for k in (
            "drawdown_curve",
            "rolling_sharpe",
            "monthly_returns",
            "weekly_returns",
            "daily_returns",
        ):
            d.pop(k, None)
        return d


def extended_report(
    equity_curve: Sequence[float],
    trades: Sequence[ClosedTrade],
    timestamps: Sequence[datetime],
    benchmark_closes: Sequence[float],
    initial_equity: float,
    years: float,
    periods_per_year: int = PERIODS_PER_YEAR,
    rolling_window: int = 30,
) -> ExtendedReport:
    """Assemble the extended analytics from one backtest's recorded outputs.

    ``timestamps`` align 1:1 with ``equity_curve`` (bar close times);
    ``benchmark_closes`` are the same-window asset closes for buy-&-hold.
    """
    strat_rets = equity_returns(equity_curve)
    bench_curve = buy_hold_curve(benchmark_closes, initial_equity)
    bench_rets = equity_returns(bench_curve)
    dd = max_drawdown(equity_curve)
    cagr_value = cagr(equity_curve, years)
    net_profit = (equity_curve[-1] - equity_curve[0]) if len(equity_curve) >= 2 else 0.0
    max_dd_abs = dd * max(equity_curve) if equity_curve else 0.0
    a, b = alpha_beta(strat_rets, bench_rets, periods_per_year)
    ts = trade_stats(trades)
    bench_total = (
        (bench_curve[-1] - bench_curve[0]) / bench_curve[0]
        if len(bench_curve) >= 2 and bench_curve[0] > 0
        else 0.0
    )
    return ExtendedReport(
        cagr=cagr_value,
        calmar=calmar_ratio(cagr_value, dd),
        recovery_factor=recovery_factor(net_profit, max_dd_abs),
        risk_of_ruin=risk_of_ruin([t.pnl for t in trades], initial_equity),
        alpha=a,
        beta=b,
        avg_win=ts.avg_win,
        avg_loss=ts.avg_loss,
        largest_win=ts.largest_win,
        largest_loss=ts.largest_loss,
        max_consecutive_wins=ts.max_consecutive_wins,
        max_consecutive_losses=ts.max_consecutive_losses,
        benchmark_total_return=bench_total,
        drawdown_curve=drawdown_curve(equity_curve),
        rolling_sharpe=rolling_sharpe(strat_rets, rolling_window, periods_per_year),
        monthly_returns=calendar_returns(timestamps, equity_curve, "ME"),
        weekly_returns=calendar_returns(timestamps, equity_curve, "W"),
        daily_returns=calendar_returns(timestamps, equity_curve, "D"),
    )
