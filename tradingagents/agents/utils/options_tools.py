from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_options_chain(
    symbol: Annotated[str, "ticker symbol of the company"],
    min_dte: Annotated[int, "minimum days to expiration"] = 0,
    max_dte: Annotated[int, "maximum days to expiration"] = 50,
) -> str:
    """
    Retrieve options chain data with Greeks and IV for a given ticker symbol.
    Returns strikes, expirations, bid/ask, volume, OI, 1st-order Greeks
    (Delta, Gamma, Theta, Vega, Rho), and implied volatility (bid_iv,
    mid_iv, ask_iv, smv_vol) filtered by DTE range.

    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSLA
        min_dte (int): Minimum days to expiration (default 0)
        max_dte (int): Maximum days to expiration (default 50)
    Returns:
        str: A formatted dataframe containing options chain data with Greeks and IV.
    """
    return route_to_vendor("get_options_chain", symbol, min_dte, max_dte)


@tool
def get_options_expirations(
    symbol: Annotated[str, "ticker symbol of the company"],
    min_dte: Annotated[int, "minimum days to expiration"] = 0,
    max_dte: Annotated[int, "maximum days to expiration"] = 50,
) -> str:
    """
    Retrieve available options expiration dates for a given ticker symbol,
    filtered by DTE range.

    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSLA
        min_dte (int): Minimum days to expiration (default 0)
        max_dte (int): Maximum days to expiration (default 50)
    Returns:
        str: Comma-separated list of expiration dates (YYYY-MM-DD format).
    """
    result = route_to_vendor("get_options_expirations", symbol, min_dte, max_dte)
    if isinstance(result, list):
        return ", ".join(result)
    return str(result)
