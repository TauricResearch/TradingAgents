"""LangChain ETF tools — vendor-agnostic via ``route_to_vendor``."""

from langchain_core.tools import tool
from typing import Annotated

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
