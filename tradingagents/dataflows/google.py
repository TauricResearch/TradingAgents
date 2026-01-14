from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
from .googlenews_utils import getNewsData


def get_google_news(
    query: Annotated[str, "Query to search with"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    query = query.replace(" ", "+")
    
    # Direct pass-through since getNewsData handles the dates
    news_results = getNewsData(query, start_date, end_date)

    news_str = ""

    for news in news_results:
        title = str(news.get('title', ''))
        source = str(news.get('source', ''))
        snippet = str(news.get('snippet', ''))
        news_str += f"### {title} (source: {source}) \n\n{snippet}\n\n"

    if len(news_results) == 0:
        return ""

    return f"## {query} Google News, from {start_date} to {end_date}:\n\n{news_str}"

def get_google_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5
) -> str:
    """
    Retrieve global news data using Google News scraper.
    Adapts the signature (curr_date, look_back_days) to (start_date, end_date).
    """
    # Calculate start date
    end_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date_dt = end_date_dt - relativedelta(days=look_back_days)
    
    start_date = start_date_dt.strftime("%Y-%m-%d")
    
    # Use a generic global market query
    query = "Global Financial Markets"
    
    return get_google_news(query, start_date, curr_date)