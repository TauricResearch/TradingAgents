"""Utility for report idempotency in scanner nodes.

Allows nodes to skip expensive LLM/Tool work if a report for the same run
already exists in the state or on disk.
"""

from __future__ import annotations

import logging

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.report_paths import get_market_dir

logger = logging.getLogger(__name__)


def require_scan_date(state: AgentState, *, node_name: str) -> str:
    """Return scan_date or fail with a deterministic pipeline error."""
    scan_date = str(state.get("scan_date") or "").strip()
    if not scan_date:
        raise RuntimeError(
            f"{node_name} missing required scan_date in graph state; "
            "scan_date must be seeded at scan start and propagated through ScannerState."
        )
    return scan_date


def require_scan_context(state: AgentState, *, node_name: str) -> tuple[str, str]:
    """Return (scan_date, run_id) or fail with a deterministic pipeline error."""
    scan_date = require_scan_date(state, node_name=node_name)
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        raise RuntimeError(
            f"{node_name} missing required run_id in graph state; "
            "run_id must be seeded at scan start and propagated through ScannerState."
        )
    return scan_date, run_id


def _read_report(path) -> str | None:
    if not path.exists():
        return None
    try:
        content = path.read_text()
        if content.strip():
            return content
    except Exception as exc:
        logger.warning("Failed to read report from disk %s: %s", path, exc)
    return None


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

    # 2. Check disk only for the explicit scan context in graph state.
    run_id = state.get("run_id")
    scan_date = state.get("scan_date")
    if run_id and scan_date:
        report_path = get_market_dir(scan_date, run_id) / f"{field}.md"
        content = _read_report(report_path)
        if content:
            return content

    return None


def save_node_report(state: AgentState, field: str, content: str) -> None:
    """Save a report to disk immediately for resumability.

    Args:
        state: The current LangGraph state (must contain run_id and scan_date).
        field: The field name to save (e.g., 'geopolitical_report').
        content: The report content to save.
    """
    scan_date, run_id = require_scan_context(state, node_name=f"save_node_report({field})")
    if not content:
        raise RuntimeError(f"save_node_report({field}) refused to persist empty content.")
    try:
        save_dir = get_market_dir(scan_date, run_id)
        save_dir.mkdir(parents=True, exist_ok=True)
        report_path = save_dir / f"{field}.md"
        report_path.write_text(content)
        logger.debug("Saved partial report to %s", report_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to save partial report for {field}: {exc}") from exc
