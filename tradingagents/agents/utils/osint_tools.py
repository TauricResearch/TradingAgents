"""Tool wrappers for OSINT data sources (Telegram, X).

These route through ``VENDOR_METHODS`` so the standard fallback chain +
``DataVendorError`` handling apply. Suitable for any analyst that uses
``llm.bind_tools(...)``.

NOTE: v0.2.5's Sentiment Analyst uses a pre-fetch pattern (no tool calls);
these wrappers are NOT auto-bound there. To use OSINT in the Sentiment
Analyst, add pre-fetch calls in ``sentiment_analyst.py`` directly (mirror
the existing news/StockTwits/Reddit blocks) and wrap them in try/except so
missing creds degrade to a placeholder instead of failing the run.
"""

from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_telegram_signals(
    query: Annotated[str, "topic/ticker to search"],
    start_date: Annotated[str, "yyyy-mm-dd"],
    end_date: Annotated[str, "yyyy-mm-dd"],
) -> str:
    """OSINT digest from curated Telegram channels for the query/date window."""
    return route_to_vendor("get_telegram_signals", query, start_date, end_date)


@tool
def get_x_signals(
    query: Annotated[str, "topic/ticker to search"],
    start_date: Annotated[str, "yyyy-mm-dd"],
    end_date: Annotated[str, "yyyy-mm-dd"],
) -> str:
    """OSINT digest from X/Twitter for the query/date window."""
    return route_to_vendor("get_x_signals", query, start_date, end_date)
