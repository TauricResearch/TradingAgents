"""Memory module implementing the FinMem pattern for TradingAgents.

This module provides a layered memory system with three scoring dimensions:
- Recency: Time-based decay for more recent memories
- Relevancy: Semantic similarity to current context
- Importance: Significance weighting for impactful events

Issue #18: Layered memory - recency, relevancy, importance scoring
"""

from .layered_memory import (
    LayeredMemory,
    MemoryEntry,
    MemoryConfig,
    ScoringWeights,
    DecayFunction,
    ImportanceLevel,
)

__all__ = [
    "LayeredMemory",
    "MemoryEntry",
    "MemoryConfig",
    "ScoringWeights",
    "DecayFunction",
    "ImportanceLevel",
]
