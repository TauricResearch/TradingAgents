"""LangChain ETF tools — vendor-agnostic via ``route_to_vendor``."""

from langchain_core.tools import tool
from typing import Annotated

from tradingagents.dataflows.etf_drilldown import (
    get_etf_top_holdings_drilldown as _drilldown_impl,
)
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_etf_profile(
    ticker: Annotated[str, "ETF ticker symbol (e.g. SPY, QQQ, 2800.HK)"],
) -> str:
    """Retrieve ETF profile: name, category, tracking strategy, AUM, expense
    ratio, fund family, asset-class breakdown, and sector weightings.

    Use this for ETF instruments instead of get_fundamentals (which targets
    company financials). The vendor is selected from the configured
    ``etf_data`` data vendor.

    Args:
        ticker (str): ETF ticker. Examples: SPY, QQQ, VOO, 2800.HK.
    Returns:
        str: Human-readable markdown block with the ETF's key profile fields.
    """
    return route_to_vendor("get_etf_profile", ticker)


@tool
def get_etf_holdings(
    ticker: Annotated[str, "ETF ticker symbol (e.g. SPY, QQQ, 2800.HK)"],
    top_n: Annotated[int, "Number of top holdings to return"] = 10,
) -> str:
    """Retrieve the top-N holdings of an ETF with weight and position size.

    Use this for ETF instruments instead of get_balance_sheet /
    get_cashflow / get_income_statement (which target company financials).

    Args:
        ticker (str): ETF ticker. Examples: SPY, QQQ, 2800.HK.
        top_n (int): Number of largest holdings to show (default 10).
    Returns:
        str: Markdown CSV with the top holdings and weights.
    """
    return route_to_vendor("get_etf_holdings", ticker, top_n)


@tool
def get_etf_top_holdings_drilldown(
    ticker: Annotated[str, "ETF ticker symbol (e.g. SPY, 2800.HK)"],
    start_date: Annotated[str, "Start date for constituent news, YYYY-MM-DD"],
    end_date: Annotated[str, "End date (also used as the fundamentals look-ahead cutoff), YYYY-MM-DD"],
    top_n: Annotated[int, "Number of top holdings to drill into (keep ≤5 to control cost)"] = 3,
) -> str:
    """Drill into an ETF's top-N constituents: for each, fetch real
    fundamentals and recent news so the analyst can reason about
    underlying-name catalysts, not just aggregate weights.

    Use sparingly — each constituent costs one fundamentals call plus one
    news call, so the default ``top_n=3`` keeps token and latency budgets
    sane. Holdings are resolved through the configured ``etf_data`` vendor
    (yfinance / alpha_vantage), and each constituent's fundamentals and
    news flow through their normal vendor (a US holding gets US-vendor
    data, a HK holding gets HK-vendor data).

    Args:
        ticker (str): ETF ticker. Examples: SPY, QQQ, 2800.HK.
        start_date (str): Start date for the news window.
        end_date (str): End date / fundamentals look-ahead cutoff.
        top_n (int): Number of top holdings to drill into (default 3).
    Returns:
        str: Markdown report with one section per top-N constituent.
    """
    return _drilldown_impl(ticker, start_date, end_date, top_n)
