from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.market_data_validator import build_verified_market_snapshot


@tool
def get_verified_market_snapshot(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[
        int,
        "Number of recent trading rows to include for sanity checking",
    ] = 30,
) -> str:
    """
    Retrieve a deterministic verification snapshot for exact market data claims.

    Returns the latest OHLCV row on or before curr_date, selected technical
    indicators, and recent closing prices. Use this before making exact claims
    about price levels, Bollinger bands, RSI, MACD, moving averages,
    support/resistance, or historical comparisons.
    """
    return build_verified_market_snapshot(symbol, curr_date, look_back_days)