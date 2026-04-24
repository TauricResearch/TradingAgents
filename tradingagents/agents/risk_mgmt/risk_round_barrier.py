"""Barrier node between parallel risk debate rounds.

This is a no-op pass-through that exists solely as a synchronization
point for LangGraph fan-in / fan-out between Round 1 and Round 2.
"""

from typing import Any, Callable


def create_risk_round_barrier() -> Callable[[dict[str, Any]], dict[str, Any]]:
    def risk_round_barrier_node(state: dict[str, Any]) -> dict[str, Any]:
        return {"sender": "risk_round_barrier"}
    return risk_round_barrier_node
