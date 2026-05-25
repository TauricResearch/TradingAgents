from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_options_chain(
    symbol: Annotated[str, "Underlying ticker symbol, e.g. AAPL"],
    expiration: Annotated[str, "Target expiration yyyy-mm-dd, or '' for the nearest expiry"] = "",
) -> str:
    """Retrieve the options chain (calls/puts with strike, last, bid/ask, volume,
    open interest, and implied volatility) for an underlying. Uses the configured
    options_data vendor. Use this to assess positioning, skew, and liquidity."""
    return route_to_vendor("get_options_chain", symbol, expiration)


@tool
def get_options_overview(
    symbol: Annotated[str, "Underlying ticker symbol, e.g. AAPL"],
) -> str:
    """Retrieve a derivatives overview for an underlying: available expirations,
    ATM implied volatility, put/call open-interest ratio, and notable strikes.
    Use this first to frame the derivatives picture before pulling a full chain."""
    return route_to_vendor("get_options_overview", symbol)
