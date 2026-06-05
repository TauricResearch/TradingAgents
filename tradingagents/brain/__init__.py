"""The brain: our multi-agent graph (wiki topology).

2 desks (Market+Sentiment, Technical+Fundamentals) -> PM aggregates -> single
Risk gate -> ResearchState. Built on the reusable infra (llm_clients, dataflows,
structured output), not on the fork's topology.
"""

from .graph import analyze_symbol, build_brain_graph
from .llm import ForkStructuredLLM, StructuredLLM
from .schemas import DeskOpinion, PMDecision, RiskDecision

__all__ = [
    "analyze_symbol",
    "build_brain_graph",
    "StructuredLLM",
    "ForkStructuredLLM",
    "DeskOpinion",
    "PMDecision",
    "RiskDecision",
]
