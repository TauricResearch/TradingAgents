from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from tradingagents.dataflows.date_window import as_of_window
from tradingagents.dataflows.truth_social import fetch_trump_truths
from tradingagents.dataflows.x_social import fetch_x_posts


@tool
def get_x_posts(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """Retrieve recent public X posts mentioning a ticker."""
    start_date, end_date = as_of_window(start_date, end_date, trade_date)
    return fetch_x_posts(ticker, start_date=start_date, end_date=end_date)


@tool
def get_trump_truths(
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    trade_date: Annotated[str, InjectedState("trade_date")] = "",
) -> str:
    """Retrieve recent posts from Donald Trump's public Truth Social timeline."""
    start_date, end_date = as_of_window(start_date, end_date, trade_date)
    return fetch_trump_truths(start_date=start_date, end_date=end_date)
