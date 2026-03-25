from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_social_sentiment(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
) -> str:
    """
    Retrieve structured social and public sentiment for a ticker.
    Uses the configured social_data vendor.
    """
    return route_to_vendor("get_social_sentiment", ticker, curr_date, look_back_days)
