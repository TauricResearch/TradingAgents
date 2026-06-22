import os
from datetime import datetime, timedelta

from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


def _bounded_date_range(start_date: str, end_date: str) -> tuple[str, str]:
    max_days = int(os.getenv("TRADINGAGENTS_TOOL_MAX_PRICE_DAYS", "90"))
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return start_date, end_date

    if end < start:
        return start_date, end_date

    bounded_start = max(start, end - timedelta(days=max_days))
    return bounded_start.strftime("%Y-%m-%d"), end_date


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
    start_date, end_date = _bounded_date_range(start_date, end_date)
    return route_to_vendor("get_stock_data", symbol, start_date, end_date)
