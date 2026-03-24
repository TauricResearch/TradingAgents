"""State definitions for the Global Macro Scanner graph."""

import operator
from typing import Annotated
from langgraph.graph import MessagesState


def _last_value(existing: str, new: str) -> str:
    """Reducer that keeps the last written value (for concurrent writes)."""
    return new


class ScannerState(MessagesState):
    """
    State for the macro scanner workflow.

    The scanner discovers interesting stocks through multiple phases:
    - Phase 1: Parallel scanners (geopolitical, market movers, sectors)
    - Phase 2: Industry deep dive (cross-references phase 1 outputs)
    - Phase 3: Macro synthesis (produces final top-10 watchlist)

    Fields written by parallel nodes use _last_value reducer to allow
    concurrent updates without LangGraph raising INVALID_CONCURRENT_GRAPH_UPDATE.
    Each parallel node writes to its own dedicated field, so no data is lost.
    """

    # Input
    scan_date: str

    # Phase 1: Parallel scanner outputs — each written by exactly one node
    geopolitical_report: Annotated[str, _last_value]
    market_movers_report: Annotated[str, _last_value]
    sector_performance_report: Annotated[str, _last_value]
    smart_money_report: Annotated[str, _last_value]

    # Phase 2: Deep dive output
    industry_deep_dive_report: Annotated[str, _last_value]

    # Phase 3: Final output
    macro_scan_summary: Annotated[str, _last_value]

    # Sender tracking — written by every node, needs reducer for parallel writes
    sender: Annotated[str, _last_value]
