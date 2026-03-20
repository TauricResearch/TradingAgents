"""Risk evaluation functions for the Portfolio Manager.

All functions are pure Python (no external dependencies).  Uses ``math.log``
for log returns and ``statistics`` stdlib for aggregation.

All monetary values are ``float``.
"""

from __future__ import annotations

import math
import statistics
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tradingagents.portfolio.models import Holding, Portfolio


# ---------------------------------------------------------------------------
# Core financial metrics
# ---------------------------------------------------------------------------


def compute_returns(prices: list[float]) -> list[float]:
    """Compute daily log returns from a price series.

    Args:
        prices: Ordered list of prices (oldest first).

    Returns:
        List of log returns (len = len(prices) - 1).
        Returns [] when fewer than 2 prices are provided.
    """
    if len(prices) < 2:
        return []
    return [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]


def sharpe_ratio(
    returns: list[float],
    risk_free_daily: float = 0.0,
) -> float | None:
    """Annualized Sharpe ratio.

    Args:
        returns: List of daily log returns.
        risk_free_daily: Daily risk-free rate (default 0).

    Returns:
        Annualized Sharpe ratio, or None if std-dev is zero or fewer than 2
        observations.
    """
    if len(returns) < 2:
        return None
    excess = [r - risk_free_daily for r in returns]
    try:
        std = statistics.stdev(excess)
    except statistics.StatisticsError:
        return None
    if std == 0.0:
        return None
    return (statistics.mean(excess) / std) * math.sqrt(252)


def sortino_ratio(
    returns: list[float],
    risk_free_daily: float = 0.0,
) -> float | None:
    """Annualized Sortino ratio (uses only downside returns for denominator).

    Args:
        returns: List of daily log returns.
        risk_free_daily: Daily risk-free rate (default 0).

    Returns:
        Annualized Sortino ratio, or None when there are no downside returns
        or fewer than 2 observations.
    """
    if len(returns) < 2:
        return None
    excess = [r - risk_free_daily for r in returns]
    downside = [r for r in excess if r < 0]
    if len(downside) < 2:
        return None
    try:
        downside_std = statistics.stdev(downside)
    except statistics.StatisticsError:
        return None
    if downside_std == 0.0:
        return None
    return (statistics.mean(excess) / downside_std) * math.sqrt(252)


def value_at_risk(
    returns: list[float],
    percentile: float = 0.05,
) -> float | None:
    """Historical Value at Risk at *percentile* (e.g. 0.05 → 5th percentile).

    Args:
        returns: List of daily log returns.
        percentile: Tail percentile in (0, 1).  Default 0.05.

    Returns:
        The *percentile* quantile of returns (a negative number means loss),
        or None when the list is empty.
    """
    if not returns:
        return None
    sorted_returns = sorted(returns)
    idx = max(0, int(math.floor(percentile * len(sorted_returns))) - 1)
    return sorted_returns[idx]


def max_drawdown(prices: list[float]) -> float | None:
    """Maximum peak-to-trough drawdown as a positive fraction.

    Args:
        prices: Ordered price (or NAV) series (oldest first).

    Returns:
        Maximum drawdown in [0, 1], or None when fewer than 2 prices.
        E.g. [100, 90, 80] → 0.2  (20 % drawdown from peak 100).
    """
    if len(prices) < 2:
        return None
    peak = prices[0]
    max_dd = 0.0
    for price in prices[1:]:
        if price > peak:
            peak = price
        dd = (peak - price) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def beta(
    asset_returns: list[float],
    benchmark_returns: list[float],
) -> float | None:
    """Compute beta of *asset_returns* relative to *benchmark_returns*.

    Beta = Cov(asset, benchmark) / Var(benchmark).

    Uses population variance / covariance (divides by n) for consistency.

    Args:
        asset_returns: Daily log returns for the asset.
        benchmark_returns: Daily log returns for the benchmark index.

    Returns:
        Beta as a float, or None when lengths mismatch, are too short, or
        benchmark variance is zero.
    """
    if len(asset_returns) != len(benchmark_returns):
        return None
    if len(asset_returns) < 2:
        return None
    bm_var = statistics.pvariance(benchmark_returns)
    if bm_var == 0.0:
        return None
    bm_mean = statistics.mean(benchmark_returns)
    asset_mean = statistics.mean(asset_returns)
    cov = statistics.mean(
        [(a - asset_mean) * (b - bm_mean) for a, b in zip(asset_returns, benchmark_returns)]
    )
    return cov / bm_var


def sector_concentration(
    holdings: list["Holding"],
    portfolio_total_value: float,
) -> dict[str, float]:
    """Compute sector concentration as a fraction of portfolio total value.

    Args:
        holdings: List of Holding objects.  ``current_value`` is used when
                  populated; otherwise ``shares * avg_cost`` is used as a proxy.
        portfolio_total_value: Total portfolio value (cash + equity).

    Returns:
        Dict mapping sector → fraction of portfolio_total_value.
        Holdings with no sector are bucketed under ``"Unknown"``.
    """
    if portfolio_total_value == 0.0:
        return {}
    sector_totals: dict[str, float] = {}
    for h in holdings:
        sector = h.sector or "Unknown"
        value = (
            h.current_value
            if h.current_value is not None
            else h.shares * h.avg_cost
        )
        sector_totals[sector] = sector_totals.get(sector, 0.0) + value
    return {s: v / portfolio_total_value for s, v in sector_totals.items()}


# ---------------------------------------------------------------------------
# Aggregate risk computation
# ---------------------------------------------------------------------------


def compute_holding_risk(
    holding: "Holding",
    price_history: list[float],
) -> dict[str, Any]:
    """Compute per-holding risk metrics.

    Args:
        holding: A Holding dataclass instance.
        price_history: Ordered list of historical closing prices for the ticker.

    Returns:
        Dict with keys: ticker, sharpe, sortino, var_5pct, max_drawdown.
    """
    returns = compute_returns(price_history)
    return {
        "ticker": holding.ticker,
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "var_5pct": value_at_risk(returns),
        "max_drawdown": max_drawdown(price_history),
    }


def compute_portfolio_risk(
    portfolio: "Portfolio",
    holdings: list["Holding"],
    price_histories: dict[str, list[float]],
    benchmark_prices: list[float] | None = None,
) -> dict[str, Any]:
    """Aggregate portfolio-level risk metrics.

    Builds a weighted portfolio return series by summing weight * log_return
    for each holding on each day.  Reconstructs a NAV series from the
    weighted returns to compute max_drawdown.

    Args:
        portfolio: Portfolio instance (cash included for weight calculation).
        holdings: List of Holding objects, enriched with current_value if
                  available.
        price_histories: Dict mapping ticker → list of closing prices.
        benchmark_prices: Optional benchmark price series for beta calculation.

    Returns:
        Dict with portfolio-level risk metrics.
    """
    total_value = portfolio.total_value or (
        portfolio.cash + sum(
            h.current_value if h.current_value is not None else h.shares * h.avg_cost
            for h in holdings
        )
    )

    # Build weighted return series
    holding_returns: dict[str, list[float]] = {}
    holding_weights: dict[str, float] = {}
    for h in holdings:
        if h.ticker not in price_histories or len(price_histories[h.ticker]) < 2:
            continue
        rets = compute_returns(price_histories[h.ticker])
        holding_returns[h.ticker] = rets
        hv = (
            h.current_value
            if h.current_value is not None
            else h.shares * h.avg_cost
        )
        holding_weights[h.ticker] = hv / total_value if total_value > 0 else 0.0

    portfolio_returns: list[float] = []
    if holding_returns:
        min_len = min(len(v) for v in holding_returns.values())
        for i in range(min_len):
            day_ret = sum(
                holding_weights[t] * holding_returns[t][i]
                for t in holding_returns
            )
            portfolio_returns.append(day_ret)

    # NAV series from portfolio returns (for drawdown)
    nav: list[float] = [1.0]
    for r in portfolio_returns:
        nav.append(nav[-1] * math.exp(r))

    bm_returns: list[float] | None = None
    if benchmark_prices and len(benchmark_prices) >= 2:
        bm_returns = compute_returns(benchmark_prices)

    portfolio_beta: float | None = None
    if bm_returns and portfolio_returns:
        n = min(len(portfolio_returns), len(bm_returns))
        portfolio_beta = beta(portfolio_returns[-n:], bm_returns[-n:])

    concentration = sector_concentration(holdings, total_value)
    holding_metrics = [
        compute_holding_risk(h, price_histories.get(h.ticker, []))
        for h in holdings
    ]

    return {
        "portfolio_sharpe": sharpe_ratio(portfolio_returns),
        "portfolio_sortino": sortino_ratio(portfolio_returns),
        "portfolio_var_5pct": value_at_risk(portfolio_returns),
        "portfolio_max_drawdown": max_drawdown(nav),
        "portfolio_beta": portfolio_beta,
        "sector_concentration": concentration,
        "num_positions": len(holdings),
        "cash_pct": portfolio.cash_pct,
        "holdings": holding_metrics,
    }


# ---------------------------------------------------------------------------
# Constraint checking
# ---------------------------------------------------------------------------


def check_constraints(
    portfolio: "Portfolio",
    holdings: list["Holding"],
    config: dict[str, Any],
    new_ticker: str | None = None,
    new_shares: float = 0,
    new_price: float = 0,
    new_sector: str | None = None,
) -> list[str]:
    """Check whether the current portfolio (or a proposed trade) violates constraints.

    Args:
        portfolio: Current Portfolio (with cash and total_value populated).
        holdings: Current list of Holding objects.
        config: Portfolio config dict (max_positions, max_position_pct,
                max_sector_pct, min_cash_pct).
        new_ticker: Ticker being considered for a new BUY (optional).
        new_shares: Shares to buy (used only with new_ticker).
        new_price: Price per share for the new BUY.
        new_sector: Sector of the new position (optional).

    Returns:
        List of human-readable violation strings.  Empty list = no violations.
    """
    violations: list[str] = []
    max_positions: int = config.get("max_positions", 15)
    max_position_pct: float = config.get("max_position_pct", 0.15)
    max_sector_pct: float = config.get("max_sector_pct", 0.35)
    min_cash_pct: float = config.get("min_cash_pct", 0.05)

    total_value = portfolio.total_value or (
        portfolio.cash + sum(
            h.current_value if h.current_value is not None else h.shares * h.avg_cost
            for h in holdings
        )
    )

    new_cost = new_shares * new_price if new_ticker else 0.0

    # --- max positions ---
    existing_tickers = {h.ticker for h in holdings}
    is_new_position = new_ticker and new_ticker not in existing_tickers
    projected_positions = len(holdings) + (1 if is_new_position else 0)
    if projected_positions > max_positions:
        violations.append(
            f"Max positions exceeded: {projected_positions} > {max_positions}"
        )

    if total_value > 0:
        # --- min cash ---
        projected_cash = portfolio.cash - new_cost
        projected_cash_pct = projected_cash / total_value
        if projected_cash_pct < min_cash_pct:
            violations.append(
                f"Min cash reserve violated: cash would be "
                f"{projected_cash_pct:.1%} < {min_cash_pct:.1%}"
            )

        # --- max position size ---
        if new_ticker and new_price > 0:
            existing_holding = next(
                (h for h in holdings if h.ticker == new_ticker), None
            )
            existing_value = (
                existing_holding.current_value
                if existing_holding and existing_holding.current_value is not None
                else (existing_holding.shares * existing_holding.avg_cost if existing_holding else 0.0)
            )
            projected_position_value = existing_value + new_cost
            position_pct = projected_position_value / total_value
            if position_pct > max_position_pct:
                violations.append(
                    f"Max position size exceeded for {new_ticker}: "
                    f"{position_pct:.1%} > {max_position_pct:.1%}"
                )

        # --- max sector exposure ---
        if new_ticker and new_sector:
            concentration = sector_concentration(holdings, total_value)
            current_sector_pct = concentration.get(new_sector, 0.0)
            projected_sector_pct = current_sector_pct + (new_cost / total_value)
            if projected_sector_pct > max_sector_pct:
                violations.append(
                    f"Max sector exposure exceeded for {new_sector}: "
                    f"{projected_sector_pct:.1%} > {max_sector_pct:.1%}"
                )

    return violations
