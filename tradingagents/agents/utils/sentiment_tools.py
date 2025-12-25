from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_fear_and_greed(
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """
    Retrieve the latest Fear and Greed Index.
    Uses the configured sentiment_analysis vendor.
    Args:
        look_back_days (int): How many days to look back, default is 30
    Returns:
        str: A formatted string containing the Fear and Greed Index.
    """
    return route_to_vendor("get_fear_and_greed", look_back_days)