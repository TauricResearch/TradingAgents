from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """
    Retrieve technical indicators for a given ticker symbol.
    Uses the configured technical_indicators vendor.
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
        indicator (str): Technical indicator to get the analysis and report of.
            Comma-separated indicator names are supported.
        curr_date (str): The current trading date you are trading on, YYYY-mm-dd
        look_back_days (int): How many days to look back, default is 30
    Returns:
        str: A formatted dataframe containing the technical indicators for the specified ticker symbol and indicator.
    """
    indicators = [item.strip().lower() for item in indicator.split(",") if item.strip()]
    results = []
    for indicator_name in indicators:
        try:
            results.append(
                route_to_vendor(
                    "get_indicators",
                    symbol,
                    indicator_name,
                    curr_date,
                    look_back_days,
                )
            )
        except ValueError as exc:
            results.append(str(exc))
    return "\n\n".join(results)
