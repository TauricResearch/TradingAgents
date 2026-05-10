from typing import Annotated

from langchain_core.tools import tool

from tradingagents.agents.utils._date_clamp import clamp, get_trade_date, maybe_note
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve news data for a given ticker symbol.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted string containing news data
    """
    s, _ = clamp(start_date, "start_date")
    e, e_clamped = clamp(end_date, "end_date")
    result = route_to_vendor("get_news", ticker, s, e)
    return maybe_note(e_clamped, "end_date") + result


@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor.
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Number of days to look back (default 7)
        limit (int): Maximum number of articles to return (default 5)
    Returns:
        str: A formatted string containing global news data
    """
    cd, was_clamped = clamp(curr_date, "curr_date")
    result = route_to_vendor("get_global_news", cd, look_back_days, limit)
    return maybe_note(was_clamped, "curr_date") + result


@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
    Returns:
        str: A report of insider transaction data
    """
    asof = get_trade_date()
    return route_to_vendor("get_insider_transactions", ticker, as_of=asof)
