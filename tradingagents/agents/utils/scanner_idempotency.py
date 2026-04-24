"""Utility for report idempotency in scanner nodes.

Allows nodes to skip expensive LLM/Tool work if a report for the same run
already exists in the state or on disk.
"""

from __future__ import annotations

import logging

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.report_paths import get_market_dir

logger = logging.getLogger(__name__)


def check_and_load_report(state: AgentState, field: str) -> str | None:
    """Check if a report exists in state or on disk.

    Args:
        state: The current LangGraph state.
        field: The field name to check (e.g., 'geopolitical_report').

    Returns:
        The report content if found, otherwise None.
    """
    # 1. Check state
    report = state.get(field)
    if report:
        return report

    # 2. Check disk if run_id and scan_date are available
    run_id = state.get("run_id")
    scan_date = state.get("scan_date")
    if run_id and scan_date:
        report_path = get_market_dir(scan_date, run_id) / f"{field}.md"
        if report_path.exists():
            try:
                content = report_path.read_text()
                if content.strip():
                    return content
            except Exception as exc:
                logger.warning("Failed to read report from disk %s: %s", report_path, exc)

    return None


def save_node_report(state: AgentState, field: str, content: str) -> None:
    """Save a report to disk immediately for resumability.

    Args:
        state: The current LangGraph state (must contain run_id and scan_date).
        field: The field name to save (e.g., 'geopolitical_report').
        content: The report content to save.
    """
    run_id = state.get("run_id")
    scan_date = state.get("scan_date")
    if run_id and scan_date and content:
        try:
            save_dir = get_market_dir(scan_date, run_id)
            save_dir.mkdir(parents=True, exist_ok=True)
            report_path = save_dir / f"{field}.md"
            report_path.write_text(content)
            logger.debug("Saved partial report to %s", report_path)
        except Exception as exc:
            logger.warning("Failed to save partial report for %s: %s", field, exc)
