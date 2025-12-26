from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_account_balance(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve the user's account balance information.
    Uses the configured profile_data vendor.
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
    Returns:
        str: A report of the user's account balance
    """
    return route_to_vendor("get_account_balance", curr_date)

@tool
def get_portfolio_holdings(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve the user's portfolio holdings information.
    Uses the configured profile_data vendor.
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
    Returns:
        str: A report of the user's portfolio holdings
    """
    return route_to_vendor("get_portfolio_holdings", curr_date)

@tool
def get_open_orders(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve the user's open orders information.
    Uses the configured profile_data vendor.
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
    Returns:
        str: A report of the user's open orders
    """
    return route_to_vendor("get_open_orders", curr_date)

@tool
def get_trade_history(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 30,
) -> str:
    """
    Retrieve the user's trade history information.
    Uses the configured profile_data vendor.
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Number of days to look back (default 30)
    Returns:
        str: A report of the user's trade history
    """
    return route_to_vendor("get_trade_history", curr_date, look_back_days)