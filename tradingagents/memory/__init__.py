"""Memory module implementing the FinMem pattern for TradingAgents.

This module provides a layered memory system with three scoring dimensions:
- Recency: Time-based decay for more recent memories
- Relevancy: Semantic similarity to current context
- Importance: Significance weighting for impactful events

Issue #18: Layered memory - recency, relevancy, importance scoring
Issue #19: Trade history memory - outcomes, agent reasoning
Issue #20: Risk profiles memory - user preferences over time
"""

from .layered_memory import (
    LayeredMemory,
    MemoryEntry,
    MemoryConfig,
    ScoringWeights,
    DecayFunction,
    ImportanceLevel,
)

from .trade_history import (
    TradeHistoryMemory,
    TradeRecord,
    TradeOutcome,
    TradeDirection,
    SignalStrength,
    AgentReasoning,
    MarketContext,
)

from .risk_profiles import (
    RiskProfileMemory,
    RiskProfile,
    RiskDecision,
    RiskTolerance,
    MarketRegime,
    RiskCategory,
)

__all__ = [
    # Layered Memory (Issue #18)
    "LayeredMemory",
    "MemoryEntry",
    "MemoryConfig",
    "ScoringWeights",
    "DecayFunction",
    "ImportanceLevel",
    # Trade History (Issue #19)
    "TradeHistoryMemory",
    "TradeRecord",
    "TradeOutcome",
    "TradeDirection",
    "SignalStrength",
    "AgentReasoning",
    "MarketContext",
    # Risk Profiles (Issue #20)
    "RiskProfileMemory",
    "RiskProfile",
    "RiskDecision",
    "RiskTolerance",
    "MarketRegime",
    "RiskCategory",
]
