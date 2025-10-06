from typing import Annotated
from langchain_core.tools import tool


@tool
def get_economic_indicators(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    lookback_days: Annotated[int, "How many days to look back for data"] = 90,
):
    """
    Retrieve comprehensive economic indicators report from FRED including:
    - Federal Funds Rate
    - Consumer Price Index (CPI) and Producer Price Index (PPI)
    - Unemployment Rate and Nonfarm Payrolls
    - GDP Growth Rate
    - ISM Manufacturing PMI
    - Consumer Confidence
    - VIX (Market Volatility)
    
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        lookback_days (int): How many days to look back for data
        
    Returns:
        str: Comprehensive economic indicators report with analysis
    """
    from tradingagents.dataflows.interface import route_to_vendor
    
    result = route_to_vendor(
        "get_economic_indicators",
        curr_date=curr_date,
        lookback_days=lookback_days
    )
    return str(result)


@tool
def get_yield_curve(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
):
    """
    Retrieve US Treasury yield curve data from FRED with inversion analysis.
    Includes yields for 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, and 30Y maturities.
    Provides 2Y-10Y spread analysis and yield curve interpretation.
    
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        
    Returns:
        str: Treasury yield curve data with analysis and recession signals
    """
    from tradingagents.dataflows.interface import route_to_vendor
    
    result = route_to_vendor(
        "get_yield_curve",
        curr_date=curr_date
    )
    return str(result)


@tool
def get_fed_calendar(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
):
    """
    Retrieve Federal Reserve meeting calendar and recent policy updates.
    Includes FOMC meeting schedule, recent Fed Funds rate history,
    and key policy considerations.
    
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        
    Returns:
        str: Fed calendar, meeting schedule, and policy trajectory
    """
    from tradingagents.dataflows.interface import route_to_vendor
    
    result = route_to_vendor(
        "get_fed_calendar",
        curr_date=curr_date
    )
    return str(result)
