from typing import Annotated

from langchain_core.tools import tool


@tool
def get_segment_fundamentals(
    ticker: Annotated[str, "company ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve company fundamentals for segment-level business mix analysis."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor("get_fundamentals", ticker=ticker, curr_date=curr_date)


@tool
def get_segment_income_statement(
    ticker: Annotated[str, "company ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    freq: Annotated[str, "financial statement frequency: quarterly or annual"] = "quarterly",
) -> str:
    """Retrieve income statement details that support segment profitability analysis."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor(
        "get_income_statement",
        ticker=ticker,
        freq=freq,
        curr_date=curr_date,
    )


@tool
def get_segment_news(
    query: Annotated[str, "segment-specific search query, including company or product line"],
    start_date: Annotated[str, "start date for search window, YYYY-MM-DD"],
    end_date: Annotated[str, "end date for search window, YYYY-MM-DD"],
) -> str:
    """Retrieve segment-relevant news that can explain demand and pricing trends."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor(
        "get_news",
        query=query,
        start_date=start_date,
        end_date=end_date,
    )
