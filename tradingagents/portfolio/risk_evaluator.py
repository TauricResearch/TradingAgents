"""Risk evaluation functions for the Portfolio Manager.

All functions are pure Python (no external dependencies).  Uses ``math.log``
for log returns and ``statistics`` stdlib for aggregation.

All monetary values are ``float``.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tradingagents.portfolio.models import Holding, Portfolio


# ---------------------------------------------------------------------------
# Core financial metrics
# ---------------------------------------------------------------------------


# Optimized: Pure-Python statistical helpers to avoid `statistics` module overhead
def _mean(values: list[float]) -> float:
    if not values:
        raise ValueError("mean requires at least one data point")
    return sum(values) / len(values)


def _std(values: list[float], ddof: int = 1) -> float:
    n = len(values)
    if n <= ddof:
        return 0.0
    mu = _mean(values)
    variance = sum((x - mu) ** 2 for x in values) / (n - ddof)
    return math.sqrt(variance)


def _pvariance(values: list[float]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    mu = _mean(values)
    return sum((x - mu) ** 2 for x in values) / n


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
    # Optimized: Compute mean and variance of excess returns in a single pass O(N)
    n = len(returns)
    if n < 2:
        return None

    sum_ex = 0.0
    sum_ex2 = 0.0

    for r in returns:
        ex = r - risk_free_daily
        sum_ex += ex
        sum_ex2 += ex * ex

    mean_ex = sum_ex / n
    variance = (sum_ex2 - sum_ex * mean_ex) / (n - 1)

    if variance <= 0.0:
        return None

    std = math.sqrt(variance)
    return (mean_ex / std) * math.sqrt(252)


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
    # Optimized: Compute mean of excess returns outside loop, evaluate downside condition directly on raw values, and use epsilon check for variance
    n = len(returns)
    if n < 2:
        return None

    mean_ex = (sum(returns) / n) - risk_free_daily

    downside_sum = 0.0
    downside_sum2 = 0.0
    downside_count = 0

    for r in returns:
        if r < risk_free_daily:
            ex = r - risk_free_daily
            downside_sum += ex
            downside_sum2 += ex * ex
            downside_count += 1

    if downside_count < 2:
        return None

    downside_mean = downside_sum / downside_count
    downside_variance = (downside_sum2 - downside_sum * downside_mean) / (downside_count - 1)

    if downside_variance <= 1e-15:
        return None

    downside_std = math.sqrt(downside_variance)
    return (mean_ex / downside_std) * math.sqrt(252)


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
    # Require at least 20 observations for a statistically meaningful VaR estimate.
    # With fewer points the percentile calculation is unreliable.
    if len(sorted_returns) < 20:
        return None
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
    # Optimized: Compute covariance and benchmark variance in a single pass O(N)
    n = len(asset_returns)
    if n != len(benchmark_returns) or n < 2:
        return None

    sum_a = sum(asset_returns)
    sum_b = sum(benchmark_returns)

    sum_ab = 0.0
    sum_b2 = 0.0

    for a, b in zip(asset_returns, benchmark_returns, strict=False):
        sum_ab += a * b
        sum_b2 += b * b

    mean_a = sum_a / n
    mean_b = sum_b / n

    cov = (sum_ab / n) - (mean_a * mean_b)
    var_b = (sum_b2 / n) - (mean_b * mean_b)

    if var_b <= 0.0:
        return None

    return cov / var_b


def sector_concentration(
    holdings: list[Holding],
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
        value = h.current_value if h.current_value is not None else h.shares * h.avg_cost
        sector_totals[sector] = sector_totals.get(sector, 0.0) + value
    return {s: v / portfolio_total_value for s, v in sector_totals.items()}


# ---------------------------------------------------------------------------
# Aggregate risk computation
# ---------------------------------------------------------------------------

_SECTOR_ETFS: dict[str, str] = {
    "technology": "XLK",
    "healthcare": "XLV",
    "financials": "XLF",
    "energy": "XLE",
    "consumer-discretionary": "XLY",
    "consumer-staples": "XLP",
    "industrials": "XLI",
    "materials": "XLB",
    "real-estate": "XLRE",
    "utilities": "XLU",
    "communication-services": "XLC",
}

_SECTOR_NORMALISE: dict[str, str] = {
    "Technology": "technology",
    "Healthcare": "healthcare",
    "Health Care": "healthcare",
    "Financial Services": "financials",
    "Financials": "financials",
    "Energy": "energy",
    "Consumer Cyclical": "consumer-discretionary",
    "Consumer Discretionary": "consumer-discretionary",
    "Consumer Defensive": "consumer-staples",
    "Consumer Staples": "consumer-staples",
    "Industrials": "industrials",
    "Basic Materials": "materials",
    "Materials": "materials",
    "Real Estate": "real-estate",
    "Utilities": "utilities",
    "Communication Services": "communication-services",
}


def compute_holding_risk(
    holding: Holding,
    price_history: list[float],
    price_histories: dict[str, list[float]] | None = None,
    benchmark_prices: list[float] | None = None,
) -> dict[str, Any]:
    """Compute per-holding risk metrics.

    Args:
        holding: A Holding dataclass instance.
        price_history: Ordered list of historical closing prices for the ticker.
        price_histories: Dict mapping ticker -> list of closing prices (used for proxy fallback).
        benchmark_prices: Optional benchmark price series for ultimate fallback.

    Returns:
        Dict with keys: ticker, sharpe, sortino, var_5pct, max_drawdown, is_proxy_risk.
    """
    if price_histories is None:
        price_histories = {}

    is_proxy_risk = False
    active_history = price_history

    if len(active_history) < 30:
        is_proxy_risk = True
        sector_key = ""
        if holding.sector:
            sector_key = _SECTOR_NORMALISE.get(
                holding.sector, holding.sector.lower().replace(" ", "-")
            )

        etf_ticker = _SECTOR_ETFS.get(sector_key)

        if etf_ticker and etf_ticker in price_histories and len(price_histories[etf_ticker]) >= 30:
            active_history = price_histories[etf_ticker]
        elif "SPY" in price_histories and len(price_histories["SPY"]) >= 30:
            active_history = price_histories["SPY"]
        elif benchmark_prices and len(benchmark_prices) >= 30:
            active_history = benchmark_prices

    returns = compute_returns(active_history)
    return {
        "ticker": holding.ticker,
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "var_5pct": value_at_risk(returns),
        "max_drawdown": max_drawdown(active_history),
        "is_proxy_risk": is_proxy_risk,
    }


def compute_portfolio_risk(
    portfolio: Portfolio,
    holdings: list[Holding],
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
        portfolio.cash
        + sum(
            h.current_value if h.current_value is not None else h.shares * h.avg_cost
            for h in holdings
        )
    )

    # Build weighted return series
    holding_returns: dict[str, list[float]] = {}
    holding_weights: dict[str, float] = {}
    for h in holdings:
        h_history = price_histories.get(h.ticker, [])
        active_history = h_history

        if len(active_history) < 30:
            sector_key = ""
            if h.sector:
                sector_key = _SECTOR_NORMALISE.get(h.sector, h.sector.lower().replace(" ", "-"))

            etf_ticker = _SECTOR_ETFS.get(sector_key)
            if (
                etf_ticker
                and etf_ticker in price_histories
                and len(price_histories[etf_ticker]) >= 30
            ):
                active_history = price_histories[etf_ticker]
            elif "SPY" in price_histories and len(price_histories["SPY"]) >= 30:
                active_history = price_histories["SPY"]
            elif benchmark_prices and len(benchmark_prices) >= 30:
                active_history = benchmark_prices

        if len(active_history) < 2:
            continue

        rets = compute_returns(active_history)
        holding_returns[h.ticker] = rets
        hv = h.current_value if h.current_value is not None else h.shares * h.avg_cost
        holding_weights[h.ticker] = hv / total_value if total_value > 0 else 0.0

    portfolio_returns: list[float] = []
    if holding_returns:
        min_len = min(len(v) for v in holding_returns.values())
        for i in range(min_len):
            day_ret = sum(holding_weights[t] * holding_returns[t][i] for t in holding_returns)
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
        compute_holding_risk(
            h,
            price_histories.get(h.ticker, []),
            price_histories=price_histories,
            benchmark_prices=benchmark_prices,
        )
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
    portfolio: Portfolio,
    holdings: list[Holding],
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
        portfolio.cash
        + sum(
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
        violations.append(f"Max positions exceeded: {projected_positions} > {max_positions}")

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
            existing_holding = next((h for h in holdings if h.ticker == new_ticker), None)
            existing_value = (
                existing_holding.current_value
                if existing_holding and existing_holding.current_value is not None
                else (
                    existing_holding.shares * existing_holding.avg_cost if existing_holding else 0.0
                )
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
