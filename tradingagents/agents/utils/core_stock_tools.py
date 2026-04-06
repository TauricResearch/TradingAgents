from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.binance import get_fibonacci_retracement as _get_fibonacci_retracement


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
    return route_to_vendor("get_stock_data", symbol, start_date, end_date)


@tool
def get_fibonacci_retracement(
    symbol: Annotated[str, "Binance trading pair, e.g. BTCUSDT or ETHUSDT"],
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "End date in YYYY-MM-DD format"],
) -> str:
    """
    Calculate Fibonacci retracement levels for a Binance trading pair.

    Computes swing high and swing low over the date range, then derives
    retracement levels at 0, 0.236, 0.382, 0.5, 0.618, and 1.0.

    Interpretation rules:
    - BTCUSDT: if the current price is ABOVE the 0.5 level → short uptrend.
    - All other coins (altcoins): if the current price is ABOVE the 0.618 level → short uptrend.

    Args:
        symbol (str): Binance trading pair, e.g. BTCUSDT, ETHUSDT
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
    Returns:
        str: Fibonacci levels table, current price zone, and trend signal.
    """
    return _get_fibonacci_retracement(symbol, start_date, end_date)
