"""Deterministic vote accounting (Constraint 2: tallies are code, not prose)."""

from __future__ import annotations

from collections.abc import Sequence

from tradingagents.contracts import (
    AgentEvidence,
    AgentVote,
    Direction,
    TradeAction,
    VoteBreakdown,
)

_DIRECTION_TO_ACTION = {
    Direction.BULLISH: TradeAction.BUY,
    Direction.BEARISH: TradeAction.SELL,
    Direction.NEUTRAL: TradeAction.HOLD,
}


def votes_from_evidence(evidence: Sequence[AgentEvidence]) -> list[AgentVote]:
    """Every evidence item is a recorded vote: its direction, its confidence."""
    return [
        AgentVote(
            agent_id=e.agent_id,
            vote=_DIRECTION_TO_ACTION[e.direction],
            confidence=e.confidence,
        )
        for e in evidence
    ]


def build_vote_breakdown(
    evidence: Sequence[AgentEvidence], judge_vote: AgentVote | None = None
) -> VoteBreakdown:
    votes = votes_from_evidence(evidence)
    if judge_vote is not None:
        votes.append(judge_vote)
    return VoteBreakdown(votes=votes)


def confidence_weighted_consensus(votes: Sequence[AgentVote]) -> tuple[TradeAction, float]:
    """Confidence-weighted plurality across BUY/SELL/HOLD.

    Returns (action, share) where share is the winning action's fraction of
    total confidence weight. Ties resolve to HOLD — a tie is not a mandate.
    """
    if not votes:
        raise ValueError("no votes to tally")
    weights = dict.fromkeys(TradeAction, 0.0)
    for vote in votes:
        weights[vote.vote] += vote.confidence
    total = sum(weights.values())
    if total == 0:
        return TradeAction.HOLD, 0.0
    best = max(weights.values())
    winners = [action for action, w in weights.items() if w == best]
    action = winners[0] if len(winners) == 1 else TradeAction.HOLD
    return action, weights[action] / total
