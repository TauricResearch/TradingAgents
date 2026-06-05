"""Wiki-aligned trading domain model.

This package is the executable form of the design specs in the project wiki:

- ``enums``  -> the 5-level Direction / conviction vocabulary + risk verdict
- ``state``  -> research_state / investment_state contract (Pydantic)
- ``risk``   -> deterministic risk engine: ATR levels, risk-based sizing,
                Statute guardrails

It is kept independent from the LangGraph wiring (that part is owned elsewhere)
so it can be developed and tested in isolation, and so the graph has a frozen
contract to build against.
"""

from .enums import Direction, RiskVerdict
from .state import AgentOpinion, Levels, ResearchState, RiskGate
from .risk import (
    SizingResult,
    atr_levels,
    check_guardrails,
    conviction_multiplier,
    passes_risk_reward,
    position_size,
    risk_reward,
)

__all__ = [
    "Direction",
    "RiskVerdict",
    "AgentOpinion",
    "Levels",
    "ResearchState",
    "RiskGate",
    "SizingResult",
    "atr_levels",
    "check_guardrails",
    "conviction_multiplier",
    "passes_risk_reward",
    "position_size",
    "risk_reward",
]
