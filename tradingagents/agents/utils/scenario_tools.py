from typing import Annotated

from langchain_core.tools import tool


@tool
def get_scenario_fundamentals(
    ticker: Annotated[str, "company ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve fundamentals context to support scenario probability framing."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor("get_fundamentals", ticker=ticker, curr_date=curr_date)


@tool
def get_scenario_news(
    query: Annotated[str, "scenario-specific catalyst query"],
    start_date: Annotated[str, "start date for search window, YYYY-MM-DD"],
    end_date: Annotated[str, "end date for search window, YYYY-MM-DD"],
) -> str:
    """Retrieve company-specific news that can update bull/base/bear probabilities."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor(
        "get_news",
        query=query,
        start_date=start_date,
        end_date=end_date,
    )


@tool
def get_catalyst_calendar(
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve policy-calendar events that can act as dated catalysts."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor("get_fed_calendar", curr_date=curr_date)
