from typing import Annotated

from langchain_core.tools import tool


@tool
def get_sizing_fundamentals(
    ticker: Annotated[str, "company ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve fundamentals that anchor conviction and portfolio sizing discipline."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor("get_fundamentals", ticker=ticker, curr_date=curr_date)


@tool
def get_sizing_price_history(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "end date in yyyy-mm-dd format"],
) -> str:
    """Retrieve recent price action used to estimate sizing bands and entry staging."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor(
        "get_stock_data",
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )


@tool
def get_sizing_indicator(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to retrieve"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """Retrieve a volatility indicator, such as ATR, for stop-distance-aware sizing."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor(
        "get_indicators",
        symbol=symbol,
        indicator=indicator,
        curr_date=curr_date,
        look_back_days=look_back_days,
    )


get_position_sizing_fundamentals = get_sizing_fundamentals
get_position_sizing_stock_data = get_sizing_price_history
get_position_sizing_indicators = get_sizing_indicator
