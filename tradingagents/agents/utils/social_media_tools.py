from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_reddit_posts(
    ticker: Annotated[str, "Ticker symbol (e.g. AAPL, TSLA)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve Reddit posts discussing a given stock ticker from social media communities
    such as r/wallstreetbets, r/stocks, r/investing, and more.
    Uses the configured social_media_data vendor.
    Args:
        ticker (str): Ticker symbol (e.g. AAPL, TSLA)
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: Formatted Reddit posts with titles, content snippets, upvotes, and dates
    """
    return route_to_vendor("get_social_media_posts", ticker, start_date, end_date)
