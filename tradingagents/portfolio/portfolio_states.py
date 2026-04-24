"""LangGraph state definition for the Portfolio Manager workflow."""

from __future__ import annotations

from typing import Annotated

from langgraph.graph import MessagesState


def _last_value(existing: str, new: str) -> str:
    """Reducer that keeps the last written value."""
    return new


class PortfolioManagerState(MessagesState):
    """State for the Portfolio Manager workflow.

    The workflow includes a parallel macro_summary/micro_summary fan-out, so
    reducer-backed string fields remain important for summary outputs and
    sender-style state writes.

    ``prices`` and ``scan_summary`` are plain dicts — written only by the
    caller (initial state) and never mutated by nodes, so no reducer needed.
    """

    # Inputs (set once by the caller, never written by nodes)
    portfolio_id: Annotated[str, _last_value]
    analysis_date: Annotated[str, _last_value]
    prices: Annotated[dict, _last_value]  # ticker → price
    scan_summary: Annotated[dict, _last_value]  # macro scan output from ScannerGraph
    ticker_analyses: Annotated[dict, _last_value]  # per-ticker analysis results keyed by ticker symbol

    # Processing fields (string-serialised JSON — written by individual nodes)
    portfolio_data: Annotated[str, _last_value]
    risk_metrics: Annotated[str, _last_value]
    holding_reviews: Annotated[str, _last_value]
    prioritized_candidates: Annotated[str, _last_value]

    # Summary briefs (written by parallel summary agents)
    macro_brief: Annotated[str, _last_value]
    micro_brief: Annotated[str, _last_value]

    # Pre-fetched memory context strings
    macro_memory_context: Annotated[str, _last_value]
    micro_memory_context: Annotated[str, _last_value]

    pm_decision: Annotated[str, _last_value]
    cash_sweep: Annotated[str, _last_value]
    execution_result: Annotated[str, _last_value]

    sender: Annotated[str, _last_value]
