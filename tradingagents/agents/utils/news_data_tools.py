from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.markets import is_nifty_50_stock

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
    return route_to_vendor("get_news", ticker, start_date, end_date)

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
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

@tool
def get_insider_sentiment(
    ticker: Annotated[str, "ticker symbol for the company"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve insider sentiment information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A report of insider sentiment data
    """
    # Check if this is an NSE stock - insider sentiment from SEC sources is not available
    if is_nifty_50_stock(ticker):
        return (f"Note: SEC-style insider sentiment data is not available for Indian NSE stocks like {ticker}. "
                f"For Indian stocks, insider trading disclosures are regulated by SEBI (Securities and Exchange Board of India) "
                f"and can be found on NSE/BSE websites or through the company's regulatory filings.")

    return route_to_vendor("get_insider_sentiment", ticker, curr_date)

@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A report of insider transaction data
    """
    return route_to_vendor("get_insider_transactions", ticker, curr_date)


@tool
def get_earnings_calendar(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve upcoming earnings and dividend calendar for a company.
    Returns next earnings date, ex-dividend date, and dividend information.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report of upcoming earnings and dividend events
    """
    return route_to_vendor("get_earnings_calendar", ticker, curr_date)
