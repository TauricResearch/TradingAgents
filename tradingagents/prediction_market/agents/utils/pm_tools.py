"""Tool definitions for prediction market agents.

Each tool is a @tool-decorated function that calls the Polymarket data layer.
"""

from langchain_core.tools import tool

from tradingagents.prediction_market.dataflows.polymarket import (
    get_polymarket_market_info,
    get_polymarket_price_history,
    get_polymarket_order_book,
    get_polymarket_resolution_criteria,
    get_polymarket_event_context,
    get_polymarket_related_markets,
    get_polymarket_search,
)


@tool
def get_market_info(market_id: str, curr_date: str) -> str:
    """Get prediction market info including question, current prices, volume, liquidity, and resolution criteria.

    Args:
        market_id: The Polymarket market/condition ID
        curr_date: Current date for reference (YYYY-MM-DD)
    """
    return get_polymarket_market_info(market_id)


@tool
def get_market_price_history(market_id: str, start_date: str, end_date: str) -> str:
    """Get historical probability time series for a prediction market.

    Args:
        market_id: The Polymarket market/condition ID
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
    """
    return get_polymarket_price_history(market_id, start_date, end_date)


@tool
def get_order_book(market_id: str) -> str:
    """Get current order book depth and spread analysis for a prediction market.

    Args:
        market_id: The Polymarket market/condition ID
    """
    return get_polymarket_order_book(market_id)


@tool
def get_resolution_criteria(market_id: str) -> str:
    """Get detailed resolution criteria, source, and timeline for a prediction market.

    Args:
        market_id: The Polymarket market/condition ID
    """
    return get_polymarket_resolution_criteria(market_id)


@tool
def get_event_context(event_id: str, curr_date: str) -> str:
    """Get all markets grouped under a prediction market event.

    Args:
        event_id: The Polymarket event ID
        curr_date: Current date for reference (YYYY-MM-DD)
    """
    return get_polymarket_event_context(event_id)


@tool
def get_related_markets(query: str, limit: int = 5) -> str:
    """Search for active prediction market events sorted by volume.

    Args:
        query: Search topic (unused for now, returns top by volume)
        limit: Maximum number of results (default 5)
    """
    return get_polymarket_related_markets(query, limit)


@tool
def search_markets(query: str, limit: int = 10) -> str:
    """Search Polymarket for markets matching a query string.

    Args:
        query: Search query (e.g. 'US election', 'Bitcoin', 'Fed rate')
        limit: Maximum number of results (default 10)
    """
    return get_polymarket_search(query, limit)
