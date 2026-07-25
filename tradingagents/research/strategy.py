"""Deterministic aggregation for independent research lenses.

This is intentionally a small domain layer, rather than a second LLM judge.
Each analytical lens supplies a bounded directional signal and confidence;
this module records the arithmetic, abstentions, and disagreement category
that the Portfolio Manager needs to see.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ConsensusLevel = Literal["unanimous", "aligned", "mixed", "abstain"]
ConflictSeverity = Literal["none", "low", "medium", "high"]


@dataclass(frozen=True)
class StrategySignal:
    """One independently-scored analytical lens.

    ``conviction=None`` means the lens abstained.  It is not a neutral (zero)
    view and therefore must never dilute a directional aggregate.
    """

    strategy_id: str
    conviction: float | None
    confidence: float
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id is required")
        if self.conviction is not None and not -1.0 <= self.conviction <= 1.0:
            raise ValueError("conviction must be in [-1, 1] or None for abstain")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")


@dataclass(frozen=True)
class StrategyConsensus:
    """Replayable result of combining strategy signals."""

    conviction: float | None
    consensus_level: ConsensusLevel
    conflict_count: int
    conflict_severity: ConflictSeverity
    participating_strategy_ids: tuple[str, ...]
    abstained_strategy_ids: tuple[str, ...]

    @property
    def disagreement(self) -> str:
        """A compact, presentation-safe PM hand-off label."""
        if self.consensus_level == "abstain":
            return "no strategy expressed a directional view"
        if self.consensus_level == "mixed":
            return f"mixed strategy views ({self.conflict_severity} disagreement)"
        return f"{self.consensus_level} strategy view"


def aggregate_strategy_signals(signals: tuple[StrategySignal, ...] | list[StrategySignal]) -> StrategyConsensus:
    """Aggregate bounded strategy signals without hiding disagreement.

    Confidence is a *reliability weight*, not a vote.  Zero-confidence signals
    remain visible as participants but cannot influence arithmetic.  An all-
    abstain result is intentionally ``None`` rather than ``0``.
    """
    seen: set[str] = set()
    participants: list[StrategySignal] = []
    abstained: list[str] = []
    for signal in signals:
        if signal.strategy_id in seen:
            raise ValueError(f"duplicate strategy_id: {signal.strategy_id}")
        seen.add(signal.strategy_id)
        if signal.conviction is None:
            abstained.append(signal.strategy_id)
        else:
            participants.append(signal)

    if not participants:
        return StrategyConsensus(
            conviction=None,
            consensus_level="abstain",
            conflict_count=0,
            conflict_severity="none",
            participating_strategy_ids=(),
            abstained_strategy_ids=tuple(abstained),
        )

    total_weight = sum(signal.confidence for signal in participants)
    # A zero-confidence signal is still auditable, but cannot be promoted to a
    # fabricated directional consensus.  Use equal weights only when every
    # lens is explicitly equally unconfident.
    weights = [signal.confidence for signal in participants]
    if total_weight == 0:
        weights = [1.0] * len(participants)
        total_weight = float(len(participants))
    conviction = sum(
        (signal.conviction or 0.0) * weight
        for signal, weight in zip(participants, weights, strict=True)
    ) / total_weight

    positive = [signal for signal in participants if (signal.conviction or 0.0) > 0]
    negative = [signal for signal in participants if (signal.conviction or 0.0) < 0]
    conflict_count = len(positive) * len(negative)
    values = [signal.conviction or 0.0 for signal in participants]
    spread = max(values) - min(values)

    if conflict_count:
        level: ConsensusLevel = "mixed"
        severity = _severity_for_spread(spread)
    elif len(participants) == 1 or spread == 0:
        level = "unanimous"
        severity = "none"
    else:
        level = "aligned"
        severity = _severity_for_spread(spread)

    return StrategyConsensus(
        conviction=round(conviction, 4),
        consensus_level=level,
        conflict_count=conflict_count,
        conflict_severity=severity,
        participating_strategy_ids=tuple(signal.strategy_id for signal in participants),
        abstained_strategy_ids=tuple(abstained),
    )


def _severity_for_spread(spread: float) -> ConflictSeverity:
    if spread < 0.25:
        return "low"
    if spread < 0.75:
        return "medium"
    return "high"
