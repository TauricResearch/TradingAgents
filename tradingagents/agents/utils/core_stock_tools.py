from typing import Annotated

from langchain_core.tools import tool

from tradingagents.agents.utils._date_clamp import clamp, maybe_note
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve stock price data (OHLCV) for a given ticker symbol.
    Uses the configured core_stock_apis vendor.
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted dataframe containing the stock price data for the specified ticker symbol in the specified date range.
    """
    s, _ = clamp(start_date, "start_date")
    e, e_clamped = clamp(end_date, "end_date")
    result = route_to_vendor("get_stock_data", symbol, s, e)
    return maybe_note(e_clamped, "end_date") + result
