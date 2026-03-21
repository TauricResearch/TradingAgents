"""Pure-Python risk metrics computation for the Portfolio Manager.

This module computes portfolio-level risk metrics from a time series of
NAV (Net Asset Value) snapshots.  It is intentionally **LLM-free** — all
calculations are deterministic Python / NumPy.

Metrics computed
----------------
- **Sharpe ratio** — annualised, risk-free rate = 0
- **Sortino ratio** — like Sharpe but denominator uses downside deviation only
- **95 % VaR** — historical simulation (5th percentile of daily returns),
  expressed as a *positive* fraction (e.g. 0.02 = 2 % expected max loss)
- **Max drawdown** — worst peak-to-trough decline as a fraction (negative)
- **Beta** — portfolio vs. an optional benchmark return series
- **Sector concentration** — weight per GICS sector (%) from the most-recent
  snapshot's ``holdings_snapshot`` field

Usage::

    from tradingagents.portfolio import compute_risk_metrics, PortfolioSnapshot

    metrics = compute_risk_metrics(snapshots, benchmark_returns=spy_returns)
    # {
    #   "sharpe": 1.23,
    #   "sortino": 1.87,
    #   "var_95": 0.018,
    #   "max_drawdown": -0.142,
    #   "beta": 0.91,
    #   "sector_concentration": {"Technology": 35.4, "Healthcare": 18.2, ...},
    #   "return_stats": {"mean_daily": 0.0008, "std_daily": 0.011, "n_days": 90},
    # }

See ``docs/portfolio/00_overview.md`` — Phase 3 for the full specification.
"""

from __future__ import annotations

import heapq
import math
from typing import Any

from tradingagents.portfolio.models import PortfolioSnapshot


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRADING_DAYS_PER_YEAR: int = 252
MIN_PERIODS_SHARPE: int = 2       # minimum data points for Sharpe / Sortino
MIN_PERIODS_VAR: int = 5          # minimum data points for VaR
MIN_PERIODS_DRAWDOWN: int = 2     # minimum data points for max drawdown
MIN_PERIODS_BETA: int = 2         # minimum data points for beta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _daily_returns(nav_series: list[float]) -> list[float]:
    """Compute daily percentage returns from an ordered NAV series.

    Returns a list one element shorter than the input.  Each element is
    ``(nav[t] - nav[t-1]) / nav[t-1]``.  Periods where the previous NAV
    is zero are skipped (appended as 0.0 to avoid division by zero).
    """
    returns: list[float] = []
    for i in range(1, len(nav_series)):
        prev = nav_series[i - 1]
        if prev == 0.0:
            returns.append(0.0)
        else:
            returns.append((nav_series[i] - prev) / prev)
    return returns


def _mean(values: list[float]) -> float:
    """Arithmetic mean of a list.  Raises ValueError on empty input."""
    if not values:
        raise ValueError("Cannot compute mean of empty list")
    return sum(values) / len(values)


def _std(values: list[float], ddof: int = 1) -> float:
    """Sample standard deviation.

    Args:
        values: List of floats.
        ddof: Degrees of freedom adjustment (1 = sample std, 0 = population).

    Returns:
        Standard deviation, or 0.0 when insufficient data.
    """
    n = len(values)
    if n <= ddof:
        return 0.0
    mu = _mean(values)
    variance = sum((x - mu) ** 2 for x in values) / (n - ddof)
    return math.sqrt(variance)


def _percentile(values: list[float], pct: float) -> float:
    """Return the *pct*-th percentile of *values* using linear interpolation.

    Args:
        values: Non-empty list of floats.
        pct: Percentile in [0, 100].

    Returns:
        Interpolated percentile value.
    """
    if not values:
        raise ValueError("Cannot compute percentile of empty list")

    n = len(values)
    # Linear interpolation index
    index = (pct / 100.0) * (n - 1)
    lower = int(index)
    upper = lower + 1
    frac = index - lower

    k_lower = lower + 1
    k_upper = n - lower

    # Small lists or k is too large to use nsmallest/nlargest efficiently -> sort
    if min(k_lower, k_upper) > 50 and min(k_lower, k_upper) > n * 0.05:
        sorted_vals = sorted(values)
        if upper >= n:
            return sorted_vals[-1]
        return sorted_vals[lower] * (1.0 - frac) + sorted_vals[upper] * frac

    if k_lower <= k_upper:
        # Use nsmallest
        k = k_lower + 1
        k_smallest = heapq.nsmallest(k, values)
        if upper >= n:
            return k_smallest[-1]
        return k_smallest[-2] * (1.0 - frac) + k_smallest[-1] * frac
    else:
        # Use nlargest
        k = k_upper
        if k == 0:
            return max(values)
        k_largest = heapq.nlargest(k, values)
        if upper >= n:
            return k_largest[-1]
        return k_largest[-1] * (1.0 - frac) + k_largest[-2] * frac


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_risk_metrics(
    snapshots: list[PortfolioSnapshot],
    benchmark_returns: list[float] | None = None,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR,
) -> dict[str, Any]:
    """Compute portfolio risk metrics from a NAV time series.

    Args:
        snapshots: Ordered list of :class:`~tradingagents.portfolio.models.PortfolioSnapshot`
            objects (oldest first).  Each snapshot contributes one NAV data
            point (``snapshot.total_value``).  At least 2 snapshots are
            required; fewer than that returns ``None`` for all rate metrics.
        benchmark_returns: Optional list of daily returns for a benchmark
            (e.g. SPY) aligned 1-to-1 with the *portfolio* daily returns
            derived from ``snapshots``.  Must be the same length as
            ``len(snapshots) - 1``.  When provided, beta is computed.
        trading_days_per_year: Number of trading days used to annualise
            Sharpe and Sortino ratios.  Defaults to 252.

    Returns:
        A dict with keys:

        - ``sharpe`` (:class:`float` | ``None``) — annualised Sharpe ratio
        - ``sortino`` (:class:`float` | ``None``) — annualised Sortino ratio
        - ``var_95`` (:class:`float` | ``None``) — 95 % historical VaR
          (positive = expected max loss as a fraction of portfolio value)
        - ``max_drawdown`` (:class:`float` | ``None``) — worst peak-to-trough
          as a fraction (negative value)
        - ``beta`` (:class:`float` | ``None``) — portfolio beta vs. benchmark
        - ``sector_concentration`` (:class:`dict[str, float]`) — sector weights
          in % from the most-recent snapshot, or ``{}`` when not available
        - ``return_stats`` (:class:`dict`) — summary stats:
          ``mean_daily``, ``std_daily``, ``n_days``

    Raises:
        TypeError: If any element of *snapshots* is not a ``PortfolioSnapshot``.
    """
    # ------------------------------------------------------------------
    # Validate input
    # ------------------------------------------------------------------
    for i, snap in enumerate(snapshots):
        if not isinstance(snap, PortfolioSnapshot):
            raise TypeError(
                f"snapshots[{i}] must be a PortfolioSnapshot, got {type(snap).__name__}"
            )

    # ------------------------------------------------------------------
    # Extract NAV series and compute daily returns
    # ------------------------------------------------------------------
    nav_series = [s.total_value for s in snapshots]
    returns = _daily_returns(nav_series)

    n_days = len(returns)

    return_stats: dict[str, Any] = {
        "mean_daily": _mean(returns) if returns else None,
        "std_daily": _std(returns) if n_days >= 2 else None,
        "n_days": n_days,
    }

    # Pre-compute mean once for reuse in Sharpe and Sortino
    mu: float | None = _mean(returns) if n_days >= MIN_PERIODS_SHARPE else None

    # ------------------------------------------------------------------
    # Sharpe ratio  (annualised, rf = 0)
    # ------------------------------------------------------------------
    sharpe: float | None = None
    if mu is not None:
        sigma = _std(returns)
        if sigma > 0.0:
            sharpe = mu / sigma * math.sqrt(trading_days_per_year)

    # ------------------------------------------------------------------
    # Sortino ratio  (downside deviation denominator)
    # ------------------------------------------------------------------
    sortino: float | None = None
    if mu is not None:
        downside = [r for r in returns if r < 0.0]
        sigma_down = _std(downside) if len(downside) >= 2 else 0.0
        if sigma_down > 0.0:
            sortino = mu / sigma_down * math.sqrt(trading_days_per_year)

    # ------------------------------------------------------------------
    # 95 % Value at Risk  (historical simulation — 5th percentile)
    # ------------------------------------------------------------------
    var_95: float | None = None
    if n_days >= MIN_PERIODS_VAR:
        # 5th-percentile return (worst end of distribution)
        fifth_pct = _percentile(returns, 5.0)
        # Express as a *positive* loss fraction
        var_95 = -fifth_pct if fifth_pct < 0.0 else 0.0

    # ------------------------------------------------------------------
    # Max drawdown  (peak-to-trough over the full window)
    # ------------------------------------------------------------------
    max_drawdown: float | None = None
    if len(nav_series) >= MIN_PERIODS_DRAWDOWN:
        peak = nav_series[0]
        worst = 0.0
        for nav in nav_series[1:]:
            if nav > peak:
                peak = nav
            if peak > 0.0:
                drawdown = (nav - peak) / peak
                if drawdown < worst:
                    worst = drawdown
        max_drawdown = worst  # 0.0 when no drawdown occurred

    # ------------------------------------------------------------------
    # Beta  (vs. benchmark, when provided)
    # ------------------------------------------------------------------
    beta: float | None = None
    if benchmark_returns is not None and len(benchmark_returns) >= MIN_PERIODS_BETA:
        # Align lengths
        min_len = min(len(returns), len(benchmark_returns))
        r_p = returns[-min_len:]
        r_b = benchmark_returns[-min_len:]
        if min_len >= MIN_PERIODS_BETA:
            mu_p = _mean(r_p)
            mu_b = _mean(r_b)
            covariance = sum(
                (r_p[i] - mu_p) * (r_b[i] - mu_b) for i in range(min_len)
            ) / (min_len - 1)
            var_b = _std(r_b) ** 2
            if var_b > 0.0:
                beta = covariance / var_b

    # ------------------------------------------------------------------
    # Sector concentration  (from last snapshot's holdings_snapshot)
    # ------------------------------------------------------------------
    sector_concentration: dict[str, float] = {}
    if snapshots:
        last_snap = snapshots[-1]
        holdings = last_snap.holdings_snapshot or []
        total_value = last_snap.total_value

        if holdings and total_value and total_value > 0.0:
            sector_totals: dict[str, float] = {}
            for h in holdings:
                sector = h.get("sector") or "Unknown"
                shares = float(h.get("shares", 0.0))
                # Use current_value if available; fall back to shares * avg_cost
                current_value = h.get("current_value")
                if current_value is not None:
                    value = float(current_value)
                else:
                    avg_cost = float(h.get("avg_cost", 0.0))
                    value = shares * avg_cost
                sector_totals[sector] = sector_totals.get(sector, 0.0) + value

            sector_concentration = {
                sector: round(total / total_value * 100.0, 2)
                for sector, total in sector_totals.items()
            }

    return {
        "sharpe": round(sharpe, 4) if sharpe is not None else None,
        "sortino": round(sortino, 4) if sortino is not None else None,
        "var_95": round(var_95, 6) if var_95 is not None else None,
        "max_drawdown": round(max_drawdown, 6) if max_drawdown is not None else None,
        "beta": round(beta, 4) if beta is not None else None,
        "sector_concentration": sector_concentration,
        "return_stats": {
            "mean_daily": round(return_stats["mean_daily"], 6)
            if return_stats["mean_daily"] is not None
            else None,
            "std_daily": round(return_stats["std_daily"], 6)
            if return_stats["std_daily"] is not None
            else None,
            "n_days": n_days,
        },
    }
