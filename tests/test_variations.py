"""Tests for graph variations: builders compile, veto enforcer rewrites correctly."""

from __future__ import annotations

import pytest
from langgraph.prebuilt import ToolNode

from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.variations import (
    VALID_VARIATIONS,
    _enforce_veto_on_decision,
    build_variation_graph,
)

pytestmark = pytest.mark.unit


def _stub_tool_nodes() -> dict:
    return {
        "market": ToolNode([]),
        "social": ToolNode([]),
        "news": ToolNode([]),
        "fundamentals": ToolNode([]),
    }


@pytest.mark.parametrize("variation", VALID_VARIATIONS)
def test_each_variation_compiles(mock_llm_client, variation):
    """Every named variation must build a compilable graph."""
    quick = mock_llm_client
    deep = mock_llm_client
    workflow = build_variation_graph(
        variation=variation,
        quick_llm=quick,
        deep_llm=deep,
        tool_nodes=_stub_tool_nodes(),
        conditional_logic=ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1),
        selected_analysts=["market", "news", "fundamentals"],
    )
    assert workflow.compile() is not None


def test_unknown_variation_raises(mock_llm_client):
    with pytest.raises(ValueError, match="Unknown variation"):
        build_variation_graph(
            variation="totally_not_real",
            quick_llm=mock_llm_client,
            deep_llm=mock_llm_client,
            tool_nodes=_stub_tool_nodes(),
            conditional_logic=ConditionalLogic(),
            selected_analysts=["market"],
        )


@pytest.mark.parametrize(
    "rating,expected",
    [
        ("Buy", "Hold"),
        ("Overweight", "Hold"),
        ("Hold", "Hold"),
        ("Underweight", "Underweight"),
        ("Sell", "Sell"),
    ],
)
def test_veto_caps_buy_and_overweight_at_hold(rating, expected):
    """Veto caps Buy/Overweight at Hold; leaves Sell/Underweight/Hold alone."""
    decision = (
        f"**Rating**: {rating}\n\n"
        "**Executive Summary**: Some plan.\n\n"
        "**Investment Thesis**: Some thesis."
    )
    out = _enforce_veto_on_decision(decision, "vol of 95% exceeds 80% ceiling.")
    assert f"**Rating**: {expected}" in out
    assert "Risk Officer Veto Applied" in out


def test_veto_no_op_when_reason_empty():
    """An empty veto reason returns the decision unchanged."""
    decision = "**Rating**: Buy\n\n**Executive Summary**: x"
    assert _enforce_veto_on_decision(decision, "") == decision
