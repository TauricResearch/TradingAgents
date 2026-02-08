from typing import Annotated, Union
from datetime import datetime
from dateutil.relativedelta import relativedelta
from .googlenews_utils import getNewsData, getGlobalNewsData
from .markets import is_nifty_50_stock, get_nifty_50_company_name


def get_google_news(
    query: Annotated[str, "Query to search with"],
    curr_date: Annotated[str, "Curr date in yyyy-mm-dd format"],
    look_back_days: Annotated[Union[int, str], "how many days to look back OR end_date string"],
) -> str:
    """
    Fetch Google News for a query.

    Note: This function handles two calling conventions:
    1. Original: (query, curr_date, look_back_days: int)
    2. From get_news interface: (ticker, start_date, end_date) where end_date is a string

    When called with end_date string, it calculates look_back_days from the date difference.
    """
    # Handle case where look_back_days is actually an end_date string (from get_news interface)
    if isinstance(look_back_days, str):
        try:
            # Called as (ticker, start_date, end_date) - need to swap and calculate
            start_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
            end_date_dt = datetime.strptime(look_back_days, "%Y-%m-%d")
            # Swap: curr_date should be end_date, calculate days difference
            actual_curr_date = look_back_days  # end_date becomes curr_date
            actual_look_back_days = (end_date_dt - start_date_dt).days
            if actual_look_back_days < 0:
                actual_look_back_days = abs(actual_look_back_days)
            curr_date = actual_curr_date
            look_back_days = actual_look_back_days
        except ValueError:
            # If parsing fails, default to 7 days
            look_back_days = 7

    # For NSE stocks, enhance query with company name for better news results
    original_query = query
    if is_nifty_50_stock(query):
        company_name = get_nifty_50_company_name(query)
        if company_name:
            # Use company name for better news search results
            # Add "NSE" and "stock" to filter for relevant financial news
            query = f"{company_name} NSE stock"

    query = query.replace(" ", "+")

    start_date = datetime.strptime(curr_date, "%Y-%m-%d")
    before = start_date - relativedelta(days=look_back_days)
    before = before.strftime("%Y-%m-%d")

    news_results = getNewsData(query, before, curr_date)

    news_str = ""

    for news in news_results:
        news_str += (
            f"### {news['title']} (source: {news['source']}) \n\n{news['snippet']}\n\n"
        )

    if len(news_results) == 0:
        return ""

    # Use original query (symbol) in the header for clarity
    display_query = original_query if is_nifty_50_stock(original_query) else query.replace("+", " ")
    return f"## {display_query} Google News, from {before} to {curr_date}:\n\n{news_str}"


def get_google_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "How many days to look back"] = 7,
    limit: Annotated[int, "Maximum number of news items to return"] = 10,
) -> str:
    """Fetch global/macro financial news via Google News RSS feed."""
    news_results = getGlobalNewsData(curr_date, look_back_days=look_back_days, limit=limit)

    if not news_results:
        return ""

    news_str = ""
    for news in news_results:
        news_str += f"### {news['title']} (source: {news['source']})\n\n{news['snippet']}\n\n"

    return f"## Global Market News (past {look_back_days} days as of {curr_date}):\n\n{news_str}"