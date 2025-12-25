from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_crypto_data(
    symbol: Annotated[str, "trading symbol, e.g., BTC/USDT"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve cryptocurrency price data (OHLCV) for a given trading symbol.
    Uses the configured core_crypto_apis vendor.
    Args:
        symbol (str): Trading symbol, e.g., BTCUSDT
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted dataframe containing the cryptocurrency price data for the specified trading symbol in the specified date range.
    """
    return route_to_vendor("get_crypto_data", symbol, start_date, end_date)
