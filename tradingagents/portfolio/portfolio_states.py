"""LangGraph state definition for the Portfolio Manager workflow."""

from __future__ import annotations

from typing import Annotated

from langgraph.graph import MessagesState


def _last_value(existing: str, new: str) -> str:
    """Reducer that keeps the last written value."""
    return new


class PortfolioManagerState(MessagesState):
    """State for the Portfolio Manager workflow.

    Sequential workflow — no parallel nodes — but all string JSON fields use
    the ``_last_value`` reducer for defensive consistency (prevents any future
    INVALID_CONCURRENT_GRAPH_UPDATE if parallelism is added later).

    ``prices`` and ``scan_summary`` are plain dicts — written only by the
    caller (initial state) and never mutated by nodes, so no reducer needed.
    """

    # Inputs (set once by the caller, never written by nodes)
    portfolio_id: str
    analysis_date: str
    prices: dict  # ticker → price
    scan_summary: dict  # macro scan output from ScannerGraph

    # Processing fields (string-serialised JSON — written by individual nodes)
    portfolio_data: Annotated[str, _last_value]
    risk_metrics: Annotated[str, _last_value]
    holding_reviews: Annotated[str, _last_value]
    prioritized_candidates: Annotated[str, _last_value]
    pm_decision: Annotated[str, _last_value]
    execution_result: Annotated[str, _last_value]

    sender: Annotated[str, _last_value]
