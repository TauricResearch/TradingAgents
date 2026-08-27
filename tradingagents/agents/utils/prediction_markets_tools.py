from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor_with_provenance


@tool
def get_prediction_markets(
    topic: Annotated[
        str,
        "Event topic/keyword, e.g. 'Fed rate cut', 'recession 2026', "
        "'US election', or a sector/company event.",
    ],
    limit: Annotated[int | None, "Max markets to return; omit for a default of 6"] = None,
    curr_date: Annotated[
        str | None,
        "Analysis cutoff in yyyy-mm-dd format; historical prediction-market snapshots are unavailable",
    ] = None,
) -> str:
    """
    Retrieve live, market-implied probabilities for forward-looking events from
    prediction markets (Polymarket): Fed decisions, recession, elections,
    geopolitics, crypto. Returns the most-traded open markets matching the
    topic, each with its implied probability, traded volume, resolution date,
    and recent move. Uses the configured prediction_markets vendor.

    Args:
        topic (str): Event keyword(s) to search
        limit (int): Max markets to return; omit for a default of 6

    Returns:
        str: A formatted markdown report of matching prediction markets
    """
    return route_to_vendor_with_provenance(
        "get_prediction_markets",
        topic,
        limit,
        analysis_cutoff=curr_date,
    )
