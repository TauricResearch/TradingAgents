from typing import Annotated

from langchain_core.tools import tool

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
    return route_to_vendor("get_news", ticker, start_date, end_date)

@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int | None, "Days to look back; omit to use the configured default"] = None,
    limit: Annotated[int | None, "Max articles to return; omit to use the configured default"] = None,
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor. Defaults for look_back_days and
    limit come from DEFAULT_CONFIG (global_news_lookback_days,
    global_news_article_limit); pass explicit values to override.

    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Number of days to look back; omit to inherit config
        limit (int): Maximum number of articles to return; omit to inherit config

    Returns:
        str: A formatted string containing global news data
    """
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

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
    return route_to_vendor("get_insider_transactions", ticker)

@tool
async def fetch_recent_news(query: str, time_range: str = "7d", limit: int = 5) -> str:
    """
    Fetches recent news articles and their full extracted text based on a search query.
    Use this tool to gather real-time financial news, market sentiment, or company updates.
    
    Args:
        query: The specific search query (e.g., "NVIDIA stock earnings", "Federal Reserve interest rates").
        time_range: The lookback period (e.g., "1d" for 1 day, "7d" for 7 days). Default is 7d.
        limit: The maximum number of articles to retrieve.
    """
    try:
        from tradingagents.dataflows.google_news import get_google_news
        # Call your new async dataflow
        articles = await get_google_news(query=query, time_range=time_range, limit=limit)
        
        if not articles:
            return f"No news found for query: '{query}' in the last {time_range}."
            
        # Format the structured Pydantic models into a clean string for the LLM
        formatted_results = []
        for i, article in enumerate(articles, 1):
            status = "[Full Text Extracted]" if article.scraped else "[RSS Summary Only]"
            formatted_results.append(
                f"### Article {i}: {article.title}\n"
                f"**Source:** {article.source} {status}\n"
                f"**Date:** {article.published_date}\n"
                f"**URL:** {article.url}\n"
                f"**Content:**\n{article.full_text}\n"
            )
            
        return "\n\n---\n\n".join(formatted_results)
        
    except Exception as e:
        return f"Error fetching news for '{query}': {str(e)}"
