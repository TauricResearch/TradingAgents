"""Barrier node between parallel risk debate rounds.

This is a no-op pass-through that exists solely as a synchronization
point for LangGraph fan-in / fan-out between Round 1 and Round 2.
"""


def create_risk_round_barrier():
    def risk_round_barrier_node(state) -> dict:
        return {"sender": "risk_round_barrier"}
    return risk_round_barrier_node
