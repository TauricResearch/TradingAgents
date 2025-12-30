from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_account_balance(
    base_coin: Annotated[str, "The base coin symbol, e.g., 'USDT'"],
    quote_coin: Annotated[str, "The quote coin symbol, e.g., 'BTC'"],
) -> str:
    """
    Fetches the account balance for a specific trading pair.
    Args:
        base_coin (str): The base coin symbol, e.g., 'USDT'
        quote_coin (str): The quote coin symbol, e.g., 'BTC'
    Returns:
        str: A formatted string containing account balance details
    """
    return route_to_vendor("get_account_balance", base_coin, quote_coin)

@tool
def get_open_orders(
    base_coin: Annotated[str, "The base coin symbol, e.g., 'USDT'"],
    quote_coin: Annotated[str, "The quote coin symbol, e.g., 'BTC'"],
) -> str:
    """
    Fetches the list of open orders for a specific trading pair.
    Args:
        base_coin (str): The base coin symbol, e.g., 'USDT'
        quote_coin (str): The quote coin symbol, e.g., 'BTC'
    Returns:
        str: A formatted string containing open orders details
    """
    return route_to_vendor("get_open_orders", base_coin, quote_coin)