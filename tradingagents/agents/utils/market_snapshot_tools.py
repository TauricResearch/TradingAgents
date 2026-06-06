from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_market_snapshot(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current trading date in YYYY-MM-DD format"],
) -> str:
    """Retrieve a freshness-aware numerical market snapshot with source provenance."""
    return route_to_vendor("get_market_snapshot", ticker, curr_date)
