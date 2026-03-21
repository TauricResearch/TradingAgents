"""LangChain tools that expose Portfolio Manager data to agents.

These tools wrap the existing Portfolio / Holding / PortfolioSnapshot data
models and the ReportStore filesystem APIs so that any LangChain-compatible
agent can:

1. **Enrich holdings** with current prices to obtain P&L, weights, and
   unrealised gain/loss — using :meth:`Holding.enrich` and
   :meth:`Portfolio.enrich`.
2. **Compute portfolio risk metrics** (Sharpe, Sortino, VaR, max drawdown,
   beta, sector concentration) from a NAV history — using the pure-Python
   :func:`~tradingagents.portfolio.risk_metrics.compute_risk_metrics`.
3. **Load saved risk metrics** from the filesystem — using
   :meth:`~tradingagents.portfolio.report_store.ReportStore.load_risk_metrics`.
4. **Load PM decisions** from the filesystem — using
   :meth:`~tradingagents.portfolio.report_store.ReportStore.load_pm_decision`.

All tools accept and return plain strings / JSON strings so they are
compatible with any LangChain tool-calling LLM without custom serialisers.

Usage::

    from tradingagents.agents.utils.portfolio_tools import (
        get_enriched_holdings,
        compute_portfolio_risk_metrics,
        load_portfolio_risk_metrics,
        load_portfolio_decision,
    )

    # In an agent's tool list:
    tools = [
        get_enriched_holdings,
        compute_portfolio_risk_metrics,
        load_portfolio_risk_metrics,
        load_portfolio_decision,
    ]
"""

from __future__ import annotations

import json
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.portfolio.models import Holding, Portfolio, PortfolioSnapshot
from tradingagents.portfolio.report_store import ReportStore
from tradingagents.portfolio.risk_metrics import compute_risk_metrics


# ---------------------------------------------------------------------------
# Tool 1 — Enrich holdings with current prices
# ---------------------------------------------------------------------------


@tool
def get_enriched_holdings(
    holdings_json: Annotated[
        str,
        "JSON array of holding objects. Each object must have: holding_id, "
        "portfolio_id, ticker, shares, avg_cost. Optional: sector, industry, "
        "created_at, updated_at.",
    ],
    prices_json: Annotated[
        str,
        "JSON object mapping ticker symbol to current market price. "
        'Example: {"AAPL": 182.50, "MSFT": 415.20}',
    ],
    portfolio_cash: Annotated[
        float,
        "Cash balance of the portfolio (USD). Used to compute cash_pct.",
    ] = 0.0,
) -> str:
    """Enrich portfolio holdings with current prices to compute P&L and weights.

    Uses the existing ``Holding.enrich()`` and ``Portfolio.enrich()`` methods
    from the portfolio data model.  For each holding the following runtime
    fields are populated:

    - ``current_price`` — latest market price
    - ``current_value`` — current_price × shares
    - ``cost_basis`` — avg_cost × shares
    - ``unrealized_pnl`` — current_value − cost_basis
    - ``unrealized_pnl_pct`` — unrealized_pnl / cost_basis (as fraction)
    - ``weight`` — current_value / total_portfolio_value (as fraction)

    Portfolio-level summary fields returned:

    - ``total_value`` — cash + sum(current_value)
    - ``equity_value`` — sum(current_value)
    - ``cash_pct`` — cash / total_value

    Args:
        holdings_json: JSON array of holding dicts (see parameter description).
        prices_json: JSON object of ticker → price mappings.
        portfolio_cash: Cash balance of the portfolio.

    Returns:
        JSON string with keys ``holdings`` (list of enriched dicts) and
        ``portfolio_summary`` (total_value, equity_value, cash, cash_pct).
    """
    try:
        raw_holdings: list[dict] = json.loads(holdings_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid holdings_json: {exc}"})

    try:
        prices: dict[str, float] = json.loads(prices_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid prices_json: {exc}"})

    # Deserialise holdings
    holdings: list[Holding] = []
    for raw in raw_holdings:
        try:
            holdings.append(Holding.from_dict(raw))
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Invalid holding record: {exc}"})

    # First pass — compute equity total for total_value
    equity = sum(
        prices.get(h.ticker, 0.0) * h.shares for h in holdings
    )
    total_value = portfolio_cash + equity

    # Second pass — enrich each holding
    enriched: list[dict] = []
    for holding in holdings:
        price = prices.get(holding.ticker)
        if price is not None:
            holding.enrich(price, total_value)
        enriched.append(
            {
                **holding.to_dict(),
                "current_price": holding.current_price,
                "current_value": holding.current_value,
                "cost_basis": holding.cost_basis,
                "unrealized_pnl": holding.unrealized_pnl,
                "unrealized_pnl_pct": holding.unrealized_pnl_pct,
                "weight": holding.weight,
            }
        )

    # Portfolio-level summary
    portfolio = Portfolio(
        portfolio_id="",
        name="",
        cash=portfolio_cash,
        initial_cash=portfolio_cash,
    )
    portfolio.enrich(holdings)

    return json.dumps(
        {
            "holdings": enriched,
            "portfolio_summary": {
                "total_value": portfolio.total_value,
                "equity_value": portfolio.equity_value,
                "cash": portfolio_cash,
                "cash_pct": portfolio.cash_pct,
            },
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool 2 — Compute risk metrics from NAV history
# ---------------------------------------------------------------------------


@tool
def compute_portfolio_risk_metrics(
    nav_history_json: Annotated[
        str,
        "JSON array of snapshot objects ordered oldest-first. Each object "
        "must have: snapshot_id, portfolio_id, snapshot_date, total_value, "
        "cash, equity_value, num_positions. Optional: holdings_snapshot "
        "(list of dicts with ticker/sector/shares/avg_cost for sector "
        "concentration), metadata.",
    ],
    benchmark_returns_json: Annotated[
        str,
        "Optional JSON array of daily benchmark returns (e.g. SPY), aligned "
        "1-to-1 with the portfolio returns derived from nav_history_json. "
        'Pass an empty JSON array "[]" to skip beta computation.',
    ] = "[]",
) -> str:
    """Compute portfolio risk metrics from a NAV (Net Asset Value) time series.

    This tool uses the pure-Python ``compute_risk_metrics()`` function from
    the Portfolio Manager's risk metrics module.  No LLM is involved.

    Metrics returned:

    - ``sharpe`` — annualised Sharpe ratio (rf = 0)
    - ``sortino`` — annualised Sortino ratio (downside deviation)
    - ``var_95`` — 95 % historical Value at Risk (positive fraction = max loss)
    - ``max_drawdown`` — worst peak-to-trough as a fraction (negative)
    - ``beta`` — portfolio beta vs. benchmark (null when no benchmark given)
    - ``sector_concentration`` — sector weights in % from the last snapshot
    - ``return_stats`` — summary: mean_daily, std_daily, n_days

    Requires at least 2 snapshots for any metrics.  Returns null for metrics
    that cannot be computed from the available data.

    Args:
        nav_history_json: JSON array of snapshot dicts (see above).
        benchmark_returns_json: JSON array of floats or ``"[]"``.

    Returns:
        JSON string containing the metrics dict, or an ``{"error": ...}``
        dict on input validation failure.
    """
    try:
        raw_snapshots: list[dict] = json.loads(nav_history_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid nav_history_json: {exc}"})

    try:
        bench_returns: list[float] = json.loads(benchmark_returns_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid benchmark_returns_json: {exc}"})

    # Deserialise snapshots
    snapshots: list[PortfolioSnapshot] = []
    for raw in raw_snapshots:
        try:
            snapshots.append(PortfolioSnapshot.from_dict(raw))
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Invalid snapshot record: {exc}"})

    try:
        metrics = compute_risk_metrics(
            snapshots,
            benchmark_returns=bench_returns if bench_returns else None,
        )
    except (TypeError, ValueError) as exc:
        return json.dumps({"error": f"Risk metrics computation failed: {exc}"})

    return json.dumps(metrics, indent=2)


# ---------------------------------------------------------------------------
# Tool 3 — Load saved risk metrics from filesystem
# ---------------------------------------------------------------------------


@tool
def load_portfolio_risk_metrics(
    portfolio_id: Annotated[str, "UUID of the portfolio."],
    date: Annotated[str, "ISO date string, e.g. '2026-03-20'."],
    reports_dir: Annotated[
        str,
        "Root reports directory. Defaults to 'reports' (relative to CWD) "
        "which matches the standard report_paths convention.",
    ] = "reports",
) -> str:
    """Load previously saved risk metrics for a portfolio on a given date.

    Uses :meth:`~tradingagents.portfolio.report_store.ReportStore.load_risk_metrics`
    to read from ``reports/daily/{date}/portfolio/{portfolio_id}_risk_metrics.json``.

    Args:
        portfolio_id: Portfolio UUID.
        date: ISO date string.
        reports_dir: Root reports directory (defaults to ``"reports"``).

    Returns:
        JSON string of the risk metrics dict, or an ``{"error": ...}`` dict
        when the file is not found or cannot be read.
    """
    store = ReportStore(base_dir=reports_dir)
    try:
        metrics = store.load_risk_metrics(date, portfolio_id)
    except Exception as exc:
        return json.dumps({"error": f"Failed to load risk metrics: {exc}"})

    if metrics is None:
        return json.dumps(
            {
                "error": (
                    f"No risk metrics found for portfolio '{portfolio_id}' "
                    f"on date '{date}'. "
                    "Run compute_portfolio_risk_metrics first and save the result."
                )
            }
        )
    return json.dumps(metrics, indent=2)


# ---------------------------------------------------------------------------
# Tool 4 — Load PM decision from filesystem
# ---------------------------------------------------------------------------


@tool
def load_portfolio_decision(
    portfolio_id: Annotated[str, "UUID of the portfolio."],
    date: Annotated[str, "ISO date string, e.g. '2026-03-20'."],
    reports_dir: Annotated[
        str,
        "Root reports directory. Defaults to 'reports'.",
    ] = "reports",
) -> str:
    """Load the Portfolio Manager agent's decision for a given date.

    Uses :meth:`~tradingagents.portfolio.report_store.ReportStore.load_pm_decision`
    to read from
    ``reports/daily/{date}/portfolio/{portfolio_id}_pm_decision.json``.

    The PM decision JSON contains the agent's allocation choices:
    sells, buys, holds, target cash %, and detailed rationale per action.

    Args:
        portfolio_id: Portfolio UUID.
        date: ISO date string.
        reports_dir: Root reports directory (defaults to ``"reports"``).

    Returns:
        JSON string of the PM decision dict, or an ``{"error": ...}`` dict
        when the file is not found.
    """
    store = ReportStore(base_dir=reports_dir)
    try:
        decision = store.load_pm_decision(date, portfolio_id)
    except Exception as exc:
        return json.dumps({"error": f"Failed to load PM decision: {exc}"})

    if decision is None:
        return json.dumps(
            {
                "error": (
                    f"No PM decision found for portfolio '{portfolio_id}' "
                    f"on date '{date}'."
                )
            }
        )
    return json.dumps(decision, indent=2)
