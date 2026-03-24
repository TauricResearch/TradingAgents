from typing import Annotated

from langchain_core.tools import tool


@tool
def get_valuation_inputs(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve valuation-oriented fundamental inputs for a company."""
    from tradingagents.dataflows.interface import route_to_vendor

    return route_to_vendor(
        "get_fundamentals",
        ticker=ticker,
        curr_date=curr_date,
    )
