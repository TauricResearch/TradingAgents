from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_yfinance_news(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve aggregated news from Yahoo Finance's curated feed for a ticker.
    Returns titles, publishers, publish times, and related tickers from multiple news sources.
    Different from get_news (Google News) — this provides Yahoo Finance's own aggregated feed.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report of curated news articles
    """
    return route_to_vendor("get_yfinance_news", ticker, curr_date)


@tool
def get_analyst_sentiment(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve analyst sentiment: price targets and recommendation distribution.
    Returns mean/median/low/high price targets, buy/sell/hold rating counts,
    and implied upside/downside vs current price.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report of analyst sentiment and price targets
    """
    return route_to_vendor("get_analyst_sentiment", ticker, curr_date)


@tool
def get_sector_performance(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve sector performance context for a ticker.
    Returns the stock's sector, its position vs moving averages, 52-week range,
    beta, and relative performance vs Nifty50 index (for Indian stocks).
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report of sector-level performance context
    """
    return route_to_vendor("get_sector_performance", ticker, curr_date)
