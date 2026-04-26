from __future__ import annotations

from datetime import UTC, datetime

from tradingagents.agents.utils.agent_states import AbortReason, AgentState


def raise_abort(
    *,
    source: str,
    reason: AbortReason,
    detail: str,
    recoverable: bool = True,
) -> dict:
    """Build a partial state update that signals a structured graph abort."""
    return {
        "abort_signal": {
            "source": source,
            "reason": reason,
            "detail": detail,
            "raised_at": datetime.now(UTC).isoformat(),
            "recoverable": recoverable,
        }
    }


def has_abort(state: AgentState) -> bool:
    return state.get("abort_signal") is not None
