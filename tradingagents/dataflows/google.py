from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
from .googlenews_utils import getNewsData


def get_google_news(
    query: Annotated[str, "Query to search with"] = None,
    ticker: Annotated[str, "Ticker symbol (alias for query)"] = None,
    curr_date: Annotated[str, "Curr date in yyyy-mm-dd format"] = None,
    look_back_days: Annotated[int, "how many days to look back"] = None,
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"] = None,
    end_date: Annotated[str, "End date in yyyy-mm-dd format"] = None,
) -> str:
    # Handle parameter aliasing (query or ticker)
    if query:
        search_query = query
    elif ticker:
        # Format ticker as a natural language query for better results
        search_query = f"latest news on {ticker} stock"
    else:
        raise ValueError("Must provide either 'query' or 'ticker' parameter")

    search_query = search_query.replace(" ", "+")

    # Determine date range
    if start_date and end_date:
        before = start_date
        target_date = end_date
    elif curr_date and look_back_days:
        target_date = curr_date
        start_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        before = (start_dt - relativedelta(days=look_back_days)).strftime("%Y-%m-%d")
    else:
        raise ValueError("Must provide either (start_date, end_date) or (curr_date, look_back_days)")

    news_results = getNewsData(search_query, before, target_date)

    news_str = ""

    for news in news_results:
        news_str += (
            f"### {news['title']} (source: {news['source']}) \n\n{news['snippet']}\n\n"
        )

    if len(news_results) == 0:
        return ""

    return f"## {search_query} Google News, from {before} to {target_date}:\n\n{news_str}"


def get_global_news_google(
    date: str,
    look_back_days: int = 3,
    limit: int = 5
) -> str:
    """Retrieve global market news using Google News.
    
    Args:
        date: Date for news, yyyy-mm-dd
        look_back_days: Days to look back
        limit: Max number of articles (not strictly enforced by underlying function but good for interface)
        
    Returns:
        Global news report
    """
    # Query for general market topics
    return get_google_news(
        query="financial markets macroeconomics",
        curr_date=date,
        look_back_days=look_back_days
    )