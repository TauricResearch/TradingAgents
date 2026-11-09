"""Phase 5 — bounded debate controller tests (contract section 6).

Each round must earn its place with new evidence, a verifiable rebuttal or
a concrete plan change; a round that repeats the opening claim stops the
debate (DEF-007). Rating disagreement and trigger disagreement are kept
distinct: only the latter (or a refuted blocking claim) stops the decision.
"""

from __future__ import annotations

from tradingagents.dataflows.debate import (
    classify_debate_outcome,
    refuted_claim_may_not_return,
    should_continue_debate,
)
from tradingagents.dataflows.fact_checker import (
    ClaimClassification,
    ClaimStatus,
    ClaimVerdict,
    FactCheckReport,
)


def _turn(speaker, round_index, evidence=(), plan=None, rating=None):
    return DebateTurnStub(speaker, round_index, tuple(evidence), plan, rating)


# A local stub so the tests do not import the dataclass constructor twice.
from tradingagents.dataflows.debate import DebateTurn as DebateTurnStub  # noqa: E402


def test_first_round_may_continue():
    stop = should_continue_debate([_turn("Bull", 1, evidence=("f1",))],
                                  max_rounds=3)
    assert stop.may_continue


def test_round_cap_stops_even_with_fresh_evidence():
    rounds = [_turn("Bull", 1, evidence=("f1",)), _turn("Bear", 1, evidence=("f2",)),
              _turn("Bull", 2, evidence=("f3",)), _turn("Bear", 2, evidence=("f4",)),
              _turn("Bull", 3, evidence=("f5",))]
    stop = should_continue_debate(rounds, max_rounds=3)
    assert not stop.may_continue
    assert stop.reason_code == "MAX_ROUNDS"


def test_repetitive_round_stops_for_redundancy():
    """DEF-007: rounds that repeat the opening claim without new evidence."""
    rounds = [
        _turn("Bull", 1, evidence=("f1",), rating="OVERWEIGHT"),
        _turn("Bear", 1, evidence=("f1",), rating="OVERWEIGHT"),
        _turn("Bull", 2, evidence=("f1",), rating="OVERWEIGHT"),  # same again
    ]
    stop = should_continue_debate(rounds, max_rounds=3)
    assert not stop.may_continue
    assert stop.stopped_for_redundancy
    assert "without new evidence" in stop.detail


def test_round_with_new_evidence_continues():
    rounds = [
        _turn("Bull", 1, evidence=("f1",)),
        _turn("Bear", 1, evidence=("f1",)),
        _turn("Bull", 2, evidence=("f1", "f2")),  # f2 is new
    ]
    stop = should_continue_debate(rounds, max_rounds=3)
    assert stop.may_continue


def test_round_with_plan_change_continues_without_new_evidence():
    """A concrete plan amendment earns a round even with the same facts."""
    rounds = [
        _turn("Bull", 1, evidence=("f1",), plan="plan-v1"),
        _turn("Bear", 1, evidence=("f1",), plan="plan-v1"),
        _turn("Bull", 2, evidence=("f1",), plan="plan-v2"),  # plan amended
    ]
    stop = should_continue_debate(rounds, max_rounds=3)
    assert stop.may_continue


def test_rating_change_earns_a_round():
    rounds = [
        _turn("Bull", 1, rating="OVERWEIGHT"),
        _turn("Bear", 1, rating="OVERWEIGHT"),
        _turn("Bull", 2, rating="NEUTRAL"),  # changed the call
    ]
    assert should_continue_debate(rounds, max_rounds=3).may_continue


def test_empty_debate_may_continue():
    assert should_continue_debate([], max_rounds=3).may_continue


# ---------------------------------------------------------------------------
# Rating vs trigger disagreement (contract §6)
# ---------------------------------------------------------------------------


def test_rating_disagreement_alone_does_not_block():
    """Bull says OVERWEIGHT, Bear says NEUTRAL: opinions may differ."""
    rounds = [
        _turn("Bull", 1, rating="OVERWEIGHT"),
        _turn("Bear", 1, rating="NEUTRAL"),
    ]
    outcome = classify_debate_outcome(rounds, trigger_agreed=True)
    assert outcome.rating_disagreement
    assert not outcome.trigger_disagreement
    assert not outcome.blocks_decision


def test_trigger_disagreement_blocks():
    rounds = [_turn("Bull", 1), _turn("Bear", 1)]
    outcome = classify_debate_outcome(rounds, trigger_agreed=False)
    assert outcome.trigger_disagreement
    assert outcome.blocks_decision


def test_refuted_blocking_claim_blocks_the_outcome():
    report = FactCheckReport()
    report.add(ClaimVerdict(
        "C-1", "absorbed the Q3", ClaimClassification.CAUSAL_INFERENCE,
        (), ClaimStatus.REFUTED, ReasonCodeStub.EVENT_AFTER_LAST_MARKET_SESSION,
        True,
    ))
    outcome = classify_debate_outcome([_turn("Bull", 1)], fact_check=report)
    assert outcome.blocks_decision


def test_refuted_claim_may_not_return():
    """The contract: a refuted blocking claim cannot be re-asserted as fact."""
    report = FactCheckReport()
    report.add(ClaimVerdict(
        "C-1", "absorbed the Q3", ClaimClassification.CAUSAL_INFERENCE,
        (), ClaimStatus.REFUTED, ReasonCodeStub.EVENT_AFTER_LAST_MARKET_SESSION,
        True,
    ))
    assert refuted_claim_may_not_return("C-1", report)
    assert not refuted_claim_may_not_return("C-999", report)


# Local import for the reason-code enum used in the stubs above.
from tradingagents.dataflows.fact_checker import ReasonCode as ReasonCodeStub  # noqa: E402
