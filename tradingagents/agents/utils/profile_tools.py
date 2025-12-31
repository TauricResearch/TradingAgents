from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_account_balance(
    symbol: Annotated[str, "The trading pair symbol, e.g., 'BTC/USDT'"],
) -> str:
    """
    Fetches the account balance for a specific trading pair.
    Args:
        symbol (str): The trading pair symbol, e.g., 'BTC/USDT'
    Returns:
        str: A formatted string containing account balance details
    """
    return route_to_vendor("get_account_balance", symbol)

@tool
def get_open_orders(
    symbol: Annotated[str, "The trading pair symbol, e.g., 'BTC/USDT'"],
) -> str:
    """
    Fetches the list of open orders for a specific trading pair.
    Args:
        symbol (str): The trading pair symbol, e.g., 'BTC/USDT'
    Returns:
        str: A formatted string containing open orders details
    """
    return route_to_vendor("get_open_orders", symbol)