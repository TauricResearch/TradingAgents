"""Phase 4 — portfolio decision separation tests (contract section 4).

The BRK-B report treated HOLD, BUY and Overweight as equivalent actions
while its own plan forbade buying at 570.89. These tests pin the separation:
an OVERWEIGHT rating coexists with a WAIT action; legacy labels map
explicitly with their original preserved; unknown labels are refused, not
guessed. Pure logic, no network, no LLM.
"""

from __future__ import annotations

import pytest

from tradingagents.dataflows.execution_gate import ExecutionAction
from tradingagents.dataflows.portfolio_decision import (
    LEGACY_RATINGS,
    StrategicDecision,
    map_legacy_rating,
    with_execution_action,
)

# ---------------------------------------------------------------------------
# Legacy mapping — explicit, label-preserving, fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_legacy_overweight_maps_to_overweight_with_label_kept():
    decision = map_legacy_rating("Overweight", "BRK-B", horizon_months=(12, 18))
    assert decision.rating == "OVERWEIGHT"
    assert decision.intent == "ACCUMULATE_CONDITIONALLY"
    assert decision.legacy_label == "Overweight"
    assert decision.horizon_months == (12, 18)


@pytest.mark.unit
def test_legacy_buy_maps_to_conditional_accumulation_not_a_market_order():
    """'Buy' the label is not 'buy now' the instruction (DEF-003)."""
    decision = map_legacy_rating("Buy", "BRK-B")
    assert decision.rating == "OVERWEIGHT"
    assert decision.intent == "ACCUMULATE_CONDITIONALLY"
    assert not decision.is_executable_action  # no action attached yet


@pytest.mark.unit
def test_legacy_hold_maps_to_neutral_maintain():
    decision = map_legacy_rating("Hold", "BRK-B")
    assert decision.rating == "NEUTRAL"
    assert decision.intent == "MAINTAIN"


@pytest.mark.unit
def test_legacy_sell_and_underweight_map_to_underweight():
    assert map_legacy_rating("Sell", "X").rating == "UNDERWEIGHT"
    assert map_legacy_rating("Underweight", "X").rating == "UNDERWEIGHT"
    assert map_legacy_rating("Sell", "X").intent == "AVOID"
    assert map_legacy_rating("Underweight", "X").intent == "REDUCE"


@pytest.mark.unit
def test_every_legacy_label_maps_and_keeps_its_label():
    """The full 5-tier scale converts; nothing is silently dropped."""
    for legacy in LEGACY_RATINGS:
        decision = map_legacy_rating(legacy, "TEST")
        assert decision.legacy_label == legacy
        assert decision.rating in ("UNDERWEIGHT", "NEUTRAL", "OVERWEIGHT")


@pytest.mark.unit
def test_unknown_legacy_label_is_refused_not_guessed():
    """An unreadable decision must be reviewed (#1170), never mapped."""
    with pytest.raises(ValueError, match="reviewed, not guessed"):
        map_legacy_rating("To the moon", "BRK-B")


@pytest.mark.unit
def test_mapping_is_case_and_space_tolerant():
    assert map_legacy_rating("  overweight ", "X").rating == "OVERWEIGHT"
    assert map_legacy_rating("HOLD", "X").rating == "NEUTRAL"


# ---------------------------------------------------------------------------
# Vocabulary separation — enforced by construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_strategic_vocabulary_rejects_action_words():
    """A rating field cannot carry an action word: the levels are distinct."""
    with pytest.raises(ValueError, match="strategic vocabulary"):
        StrategicDecision(ticker="X", rating="BUY", intent="MAINTAIN")
    with pytest.raises(ValueError, match="strategic vocabulary"):
        StrategicDecision(ticker="X", rating="WAIT", intent="MAINTAIN")


@pytest.mark.unit
def test_intent_vocabulary_rejects_non_intents():
    with pytest.raises(ValueError, match="intent vocabulary"):
        StrategicDecision(ticker="X", rating="NEUTRAL", intent="BUY NOW")


@pytest.mark.unit
def test_horizon_must_be_ordered():
    with pytest.raises(ValueError, match="horizon"):
        StrategicDecision(ticker="X", rating="NEUTRAL", intent="MAINTAIN",
                          horizon_months=(18, 12))
    # A valid horizon passes.
    ok = StrategicDecision(ticker="X", rating="NEUTRAL", intent="MAINTAIN",
                           horizon_months=(0, 6))
    assert ok.horizon_months == (0, 6)


# ---------------------------------------------------------------------------
# OVERWEIGHT coexists with WAIT — the contract's core separation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overweight_rating_with_wait_action_coexists():
    """The BRK-B shape: bullish opinion, no executable step (contract §4)."""
    decision = map_legacy_rating("Overweight", "BRK-B", horizon_months=(12, 18))
    gated = with_execution_action(
        decision, ExecutionAction.WAIT,
        ("ENTRY_TRIGGER_NOT_MET", "POST_EARNINGS_REACTION_UNOBSERVABLE"),
    )
    assert gated.rating == "OVERWEIGHT"
    assert gated.execution_action is ExecutionAction.WAIT
    assert not gated.is_executable_action
    assert gated.reason_codes == (
        "ENTRY_TRIGGER_NOT_MET", "POST_EARNINGS_REACTION_UNOBSERVABLE",
    )


@pytest.mark.unit
def test_action_attachment_preserves_the_strategic_levels():
    decision = map_legacy_rating("Buy", "AAPL")
    gated = with_execution_action(decision, ExecutionAction.PROPOSE_PAPER_ORDER, ("OK",))
    assert gated.rating == decision.rating
    assert gated.intent == decision.intent
    assert gated.legacy_label == decision.legacy_label
    assert gated.is_executable_action


@pytest.mark.unit
def test_block_action_is_not_executable():
    decision = map_legacy_rating("Overweight", "BRK-B")
    gated = with_execution_action(decision, ExecutionAction.BLOCK, ("DATA_QUALITY_BLOCKED",))
    assert gated.execution_action is ExecutionAction.BLOCK
    assert not gated.is_executable_action


# ---------------------------------------------------------------------------
# Rendering — the three levels visibly distinct
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_render_shows_all_three_levels_and_the_caveat():
    decision = map_legacy_rating("Overweight", "BRK-B", horizon_months=(12, 18))
    gated = with_execution_action(decision, ExecutionAction.WAIT, ("ENTRY_TRIGGER_NOT_MET",))
    text = gated.render()
    assert "**Strategic rating**: OVERWEIGHT (legacy label: Overweight)" in text
    assert "**Investment intent**: ACCUMULATE_CONDITIONALLY" in text
    assert "**Horizon**: 12-18 months" in text
    assert "**Execution action**: WAIT" in text
    assert "does not authorize a market order" in text


@pytest.mark.unit
def test_render_without_action_or_horizon_is_explicit():
    decision = map_legacy_rating("Hold", "X")
    text = decision.render()
    assert "**Execution action**: not evaluated" in text
    assert "**Horizon**: not provided" in text
    assert "Reason codes**: none" in text
