"""Tests for the Portfolio Manager / risk-stage finalisation in runner.py.

These tests cover two regressions that surfaced together:

1. The ``risk`` stage showed as "running" in the UI even after the run
   completed, because the runner never emitted an ``analyst_completed``
   event with a report for the risk stage.  The Portfolio Manager
   synthesises the risk debate and writes the final decision, so it must
   appear in ``_STAGE_MAP`` and emit an ``analyst_completed`` that
   carries the decision markdown as the report.

2. The runner read ``final_state["decision"]`` as a dict, but the
   framework stores the decision as a markdown string under
   ``final_state["final_trade_decision"]`` and returns the parsed rating
   (``Buy`` / ``Overweight`` / ``Hold`` / ``Underweight`` / ``Sell``)
   as the second tuple element of ``propagate()``.  The runner needs a
   helper that turns those two inputs into the ``{action, target,
   rationale, confidence}`` shape the API and frontend consume.
"""
import pytest

from web.server import runner


def test_stage_map_includes_portfolio_manager_as_risk_consolidator():
    """The Portfolio Manager is the node that finalises the risk stage.

    Without this entry, the runner never emits ``analyst_completed``
    with a report for the risk stage, and the UI shows the stage as
    "running" forever.
    """
    assert "Portfolio Manager" in runner._STAGE_MAP
    stage, report_field = runner._STAGE_MAP["Portfolio Manager"]
    assert stage == "risk"
    assert report_field == "final_trade_decision"


def test_parse_pm_decision_hold():
    state = {
        "final_trade_decision": (
            "**Rating**: Hold\n\n"
            "**Executive Summary**: Maintain current position.\n\n"
            "**Investment Thesis**: Mixed signals across the board."
        )
    }
    out = runner._parse_pm_decision(state, "Hold")
    assert out["action"] == "HOLD"
    assert out["target"] is None
    assert "Hold" in out["rationale"]
    assert "Investment Thesis" in out["rationale"]
    assert out["confidence"] == pytest.approx(0.5)


def test_parse_pm_decision_buy_with_price_target():
    state = {
        "final_trade_decision": (
            "**Rating**: Buy\n\n"
            "**Executive Summary**: Strong conviction.\n\n"
            "**Investment Thesis**: AI memory growth.\n\n"
            "**Price Target**: 150.5\n\n"
            "**Time Horizon**: 3-6 months"
        )
    }
    out = runner._parse_pm_decision(state, "Buy")
    assert out["action"] == "BUY"
    assert out["target"] == 150.5
    assert out["confidence"] == pytest.approx(0.9)


def test_parse_pm_decision_overweight_maps_to_buy():
    state = {"final_trade_decision": "**Rating**: Overweight\n..."}
    out = runner._parse_pm_decision(state, "Overweight")
    assert out["action"] == "BUY"
    assert out["confidence"] == pytest.approx(0.7)


def test_parse_pm_decision_sell():
    state = {"final_trade_decision": "**Rating**: Sell\n..."}
    out = runner._parse_pm_decision(state, "Sell")
    assert out["action"] == "SELL"
    assert out["target"] is None
    assert out["confidence"] == pytest.approx(0.1)


def test_parse_pm_decision_underweight_maps_to_sell():
    state = {"final_trade_decision": "**Rating**: Underweight\n..."}
    out = runner._parse_pm_decision(state, "Underweight")
    assert out["action"] == "SELL"
    assert out["confidence"] == pytest.approx(0.3)


def test_parse_pm_decision_missing_markdown_returns_hold():
    """Defensive: if the framework returns no markdown, default to HOLD."""
    out = runner._parse_pm_decision({}, "Hold")
    assert out["action"] == "HOLD"
    assert out["target"] is None
    assert out["confidence"] == pytest.approx(0.5)
    assert out["rationale"] == ""


def test_parse_pm_decision_unknown_rating_falls_back_to_hold():
    """Defensive: if propagate returns a non-5-tier rating, hold the line."""
    out = runner._parse_pm_decision({"final_trade_decision": "weird"}, "??")
    assert out["action"] == "HOLD"
    assert out["confidence"] == pytest.approx(0.5)


def test_parse_pm_decision_extracts_target_from_inline_action_header():
    """The model often puts the target inline in the decision header
    (``BUY at $4,000``) instead of in the structured ``**Price Target**``
    field.  This was the DELL run: the LLM said ``BUY at $4,000`` and
    the runner saved ``decision_target: null`` because the old regex
    only matched the structured field.
    """
    state = {
        "final_trade_decision": (
            "**Final Trading Decision: BUY at $4,000 (with a 10% equity position)**  \n"
            "**Exchange**: `.NYQ.L`\n\n"
            "**Rationale**: Strong fundamentals...\n\n"
            "**Strategic Actions**:\n"
            "- Position 10% at 3000 USD.\n"  # position sizing, NOT the target
            "- Exit at 2020 Q3 earnings.\n"
        )
    }
    out = runner._parse_pm_decision(state, "Buy")
    assert out["action"] == "BUY"
    assert out["target"] == 4000.0


def test_parse_pm_decision_structured_price_target_wins_over_inline():
    """When both are present, the structured field is more reliable
    than the inline header (which can be malformed or absent in
    downstream renders).
    """
    state = {
        "final_trade_decision": (
            "**Rating**: Buy\n\n"
            "**Final Trading Decision: BUY at $4,000**\n\n"
            "**Price Target**: 425.50\n"
        )
    }
    out = runner._parse_pm_decision(state, "Buy")
    assert out["target"] == 425.5


def test_parse_pm_decision_no_target_anywhere_returns_none():
    """MSTR-style: model emits 'BUY MSTR' with no target anywhere.
    The parser must not invent a number from position-sizing text.
    """
    state = {
        "final_trade_decision": (
            "**Rating**: Buy\n\n"
            "**Final Trading Decision**: **BUY MSTR**.\n\n"
            "**Key Reasoning**: MACD divergence supports upward momentum.\n\n"
            "**Position Sizing**: 5% allocation.\n"
        )
    }
    out = runner._parse_pm_decision(state, "Buy")
    assert out["action"] == "BUY"
    assert out["target"] is None


def test_parse_pm_decision_sell_inline_target():
    state = {
        "final_trade_decision": "**Final Trading Decision: SELL at $12.34**"
    }
    out = runner._parse_pm_decision(state, "Sell")
    assert out["action"] == "SELL"
    assert out["target"] == 12.34
