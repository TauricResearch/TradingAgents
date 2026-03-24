from typing import Annotated

from langchain_core.tools import tool


@tool
def get_economic_indicators(
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    lookback_days: Annotated[int, "how many days to look back for data"] = 90,
) -> str:
    """Retrieve a macro indicators report backed by the configured macro data vendor."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor(
        "get_economic_indicators",
        curr_date=curr_date,
        lookback_days=lookback_days,
    )


@tool
def get_yield_curve(
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve the US Treasury yield curve and spread analysis."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor("get_yield_curve", curr_date=curr_date)


@tool
def get_fed_calendar(
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve the recent Federal Reserve policy path summary."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor("get_fed_calendar", curr_date=curr_date)
