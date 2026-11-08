"""Bounded debate controller (Phase 5, contract section 6).

The existing debate runs a fixed number of rounds; the contract requires
each round to earn its place with **new evidence, a verifiable rebuttal, or
a concrete change to the plan** — otherwise the debate stops for
convergence/redundancy. This module adds that test as a pure function the
graph's conditional logic can consult, without changing the graph wiring.

It also keeps the contract's distinction between disagreement about the
*rating* (a strategic opinion, allowed to persist) and disagreement about
the *execution trigger* (a checkable fact, must be resolved or the plan
waits/blocks).
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingagents.dataflows.fact_checker import ClaimStatus, FactCheckReport


@dataclass(frozen=True)
class DebateTurn:
    """One speaker's turn, reduced to what the stopping test may use.

    ``evidence_ids`` are the fact ids the turn newly cites; ``plan_hash``
    changes when the speaker concretely amended the plan (levels, sizes,
    triggers); ``rating`` is the speaker's strategic rating this turn.
    """

    speaker: str
    round_index: int
    evidence_ids: tuple[str, ...] = ()
    plan_hash: str | None = None
    rating: str | None = None


@dataclass(frozen=True)
class DebateStop:
    """Whether the debate may continue, and why not."""

    may_continue: bool
    reason_code: str
    detail: str

    @property
    def stopped_for_redundancy(self) -> bool:
        return self.reason_code == "NO_NEW_EVIDENCE"


def _turns_in(rounds: list[DebateTurn], index: int) -> list[DebateTurn]:
    return [t for t in rounds if t.round_index == index]


def should_continue_debate(
    rounds: list[DebateTurn],
    *,
    max_rounds: int,
) -> DebateStop:
    """Whether another round is justified (contract §6: rounds must earn it).

    A round is redundant when it adds no evidence id, no plan change and no
    rating change over every earlier round — the "repeating the opening
    claim" failure (DEF-007). The round cap still applies first: no debate
    exceeds ``max_rounds`` even with fresh evidence.
    """
    if not rounds:
        return DebateStop(True, "OK", "no turns yet")
    current = max(t.round_index for t in rounds)
    if current >= max_rounds:
        return DebateStop(False, "MAX_ROUNDS",
                          f"round cap {max_rounds} reached")
    seen_evidence: set[str] = set()
    seen_plans: set[str] = set()
    seen_ratings: set[str] = set()
    for turn in rounds:
        if turn.round_index >= current:
            break
        seen_evidence.update(turn.evidence_ids)
        if turn.plan_hash is not None:
            seen_plans.add(turn.plan_hash)
        if turn.rating is not None:
            seen_ratings.add(turn.rating)
    current_turns = _turns_in(rounds, current)
    new_evidence = any(fid not in seen_evidence
                       for t in current_turns for fid in t.evidence_ids)
    new_plan = any(t.plan_hash is not None and t.plan_hash not in seen_plans
                   for t in current_turns)
    new_rating = any(t.rating is not None and t.rating not in seen_ratings
                     for t in current_turns)
    if new_evidence or new_plan or new_rating:
        return DebateStop(True, "OK", "the round added evidence, a plan change or a rating change")
    return DebateStop(
        False, "NO_NEW_EVIDENCE",
        "the round repeated earlier claims without new evidence, a verifiable "
        "rebuttal or a concrete plan change",
    )


@dataclass(frozen=True)
class DebateOutcome:
    """The debate's end state, split the way the contract requires."""

    rating_disagreement: bool      # strategic opinions may differ: allowed
    trigger_disagreement: bool     # a checkable fact: must resolve or gate
    fact_check: FactCheckReport | None
    stop: DebateStop

    @property
    def blocks_decision(self) -> bool:
        """Only an unresolved trigger disagreement or a blocking refuted
        claim stops the decision; a rating disagreement never does."""
        if self.trigger_disagreement:
            return True
        return self.fact_check is not None and self.fact_check.blocks_decision


def classify_debate_outcome(
    rounds: list[DebateTurn],
    *,
    fact_check: FactCheckReport | None = None,
    trigger_agreed: bool = True,
) -> DebateOutcome:
    """Split the debate's disagreement into rating vs trigger (contract §6).

    ``trigger_agreed`` is the speakers' own resolution of the checkable
    question (is the entry condition met, is the data valid). Rating
    disagreement is read from the turns: differing ratings across the last
    round's speakers.
    """
    last_index = max((t.round_index for t in rounds), default=0)
    last_ratings = {t.rating for t in _turns_in(rounds, last_index) if t.rating}
    rating_disagreement = len(last_ratings) > 1
    stop = should_continue_debate(rounds, max_rounds=max(rounds[-1].round_index + 1 if rounds else 1,
                                                         1))
    return DebateOutcome(
        rating_disagreement=rating_disagreement,
        trigger_disagreement=not trigger_agreed,
        fact_check=fact_check,
        stop=stop,
    )


def refuted_claim_may_not_return(
    claim_id: str,
    fact_check: FactCheckReport,
) -> bool:
    """Whether a claim was refuted and so may not be re-asserted as fact.

    The contract: a refuted blocking claim cannot be reported as fact by
    the Portfolio Manager. This is the checkable form of that rule.
    """
    for verdict in fact_check.verdicts:
        if verdict.claim_id == claim_id:
            return verdict.status is ClaimStatus.REFUTED
    return False
