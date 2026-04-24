from __future__ import annotations

from tradingagents.agents.utils.agent_states import AgentState

CRITICAL_ABORT_PREFIX = "[CRITICAL ABORT]"


def report_has_critical_abort(report: str) -> bool:
    """Return True only when the report starts with the explicit abort marker."""
    if not report:
        return False
    return str(report).lstrip().startswith(CRITICAL_ABORT_PREFIX)


def state_has_critical_abort(state: AgentState, /, *report_fields: str) -> bool:
    """Return True when any named report field begins with the abort marker."""
    return any(report_has_critical_abort(state.get(field, "")) for field in report_fields)


def extract_abort_report(*report_fields: str) -> tuple[str, str]:

    """Return the first aborting report field and its raw text."""
    for field in report_fields:
        report = state.get(field, "")
        if report_has_critical_abort(report):
            return field, report
    return "", ""
