"""Barrier node between parallel risk debate rounds.

This is a no-op pass-through that exists solely as a synchronization
point for LangGraph fan-in / fan-out between Round 1 and Round 2.
"""

from collections.abc import Callable
from typing import Any

from tradingagents.agents.utils.agent_states import AgentState


def create_risk_round_barrier() -> Callable[[AgentState], dict[str, Any]]:
    def risk_round_barrier_node(state: AgentState) -> dict[str, Any]:

        return {"sender": "risk_round_barrier"}
    return risk_round_barrier_node
