"""Scanner tools for market-wide analysis."""

from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_market_movers(
    category: Annotated[str, "Category: 'day_gainers', 'day_losers', or 'most_actives'"],
) -> str:
    """
    Get top market movers (gainers, losers, or most active stocks).
    Uses the configured scanner_data vendor.
    
    Args:
        category (str): Category of market movers - 'day_gainers', 'day_losers', or 'most_actives'
        
    Returns:
        str: Formatted table of top market movers with symbol, price, change %, volume, market cap
    """
    return route_to_vendor("get_market_movers", category)


@tool
def get_market_indices() -> str:
    """
    Get major market indices data (S&P 500, Dow Jones, NASDAQ, VIX, Russell 2000).
    Uses the configured scanner_data vendor.
    
    Returns:
        str: Formatted table of index values with current price, daily change, 52W high/low
    """
    return route_to_vendor("get_market_indices")


@tool
def get_sector_performance() -> str:
    """
    Get sector-level performance overview for all 11 GICS sectors.
    Uses the configured scanner_data vendor.
    
    Returns:
        str: Formatted table of sector performance with 1-day, 1-week, 1-month, and YTD returns
    """
    return route_to_vendor("get_sector_performance")


@tool
def get_industry_performance(
    sector_key: Annotated[str, "Sector key (e.g., 'technology', 'healthcare', 'financial-services')"],
) -> str:
    """
    Get industry-level drill-down within a specific sector.
    Shows top companies and industries in the sector.
    Uses the configured scanner_data vendor.
    
    Args:
        sector_key (str): Sector identifier (e.g., 'technology', 'healthcare', 'energy')
        
    Returns:
        str: Formatted table of top companies/industries in the sector with performance data
    """
    return route_to_vendor("get_industry_performance", sector_key)


@tool
def get_topic_news(
    topic: Annotated[str, "Search topic/query (e.g., 'artificial intelligence', 'semiconductor', 'renewable energy')"],
    limit: Annotated[int, "Maximum number of articles to return"] = 10,
) -> str:
    """
    Search news by arbitrary topic for market-wide analysis.
    Uses the configured scanner_data vendor.
    
    Args:
        topic (str): Search query/topic for news
        limit (int): Maximum number of articles to return (default 10)
        
    Returns:
        str: Formatted list of news articles for the topic with title, summary, source, and link
    """
    return route_to_vendor("get_topic_news", topic, limit)
