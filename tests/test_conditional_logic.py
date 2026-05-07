"""Lock down conditional_logic.py routing behavior.

These tests don't change the existing logic. They establish that the routing
is `tool_calls`-based (not string-matching on FINAL TRANSACTION PROPOSAL),
which means the same routing works for both stock and polymarket modes.
"""

from unittest.mock import MagicMock
import pytest

from tradingagents.graph.conditional_logic import ConditionalLogic


def _make_state(*, has_tool_calls: bool, debate_count: int = 0, last_speaker: str = ""):
    """Build a minimal state dict matching what each routing function reads."""
    msg = MagicMock()
    msg.tool_calls = [{"name": "tool"}] if has_tool_calls else []
    return {
        "messages": [msg],
        "investment_debate_state": {
            "count": debate_count,
            "current_response": last_speaker,
        },
        "risk_debate_state": {
            "count": debate_count,
            "latest_speaker": last_speaker,
        },
    }


@pytest.mark.unit
def test_market_routing_uses_tool_calls():
    """Market analyst routes to tools when LLM made a tool call."""
    cl = ConditionalLogic()
    assert cl.should_continue_market(_make_state(has_tool_calls=True)) == "tools_market"
    assert cl.should_continue_market(_make_state(has_tool_calls=False)) == "Msg Clear Market"


@pytest.mark.unit
def test_news_routing_uses_tool_calls():
    """News analyst routes to tools when LLM made a tool call."""
    cl = ConditionalLogic()
    assert cl.should_continue_news(_make_state(has_tool_calls=True)) == "tools_news"
    assert cl.should_continue_news(_make_state(has_tool_calls=False)) == "Msg Clear News"


@pytest.mark.unit
def test_social_routing_uses_tool_calls():
    """Social analyst routes the same way."""
    cl = ConditionalLogic()
    assert cl.should_continue_social(_make_state(has_tool_calls=True)) == "tools_social"
    assert cl.should_continue_social(_make_state(has_tool_calls=False)) == "Msg Clear Social"


@pytest.mark.unit
def test_fundamentals_routing_uses_tool_calls():
    """Fundamentals analyst routes the same way (used as probability_analyst in PM mode)."""
    cl = ConditionalLogic()
    assert cl.should_continue_fundamentals(_make_state(has_tool_calls=True)) == "tools_fundamentals"
    assert cl.should_continue_fundamentals(_make_state(has_tool_calls=False)) == "Msg Clear Fundamentals"


@pytest.mark.unit
def test_debate_terminates_at_max_rounds():
    """Debate routes to Research Manager when round limit hit."""
    cl = ConditionalLogic(max_debate_rounds=1)
    state = _make_state(has_tool_calls=False, debate_count=2, last_speaker="Bull")
    assert cl.should_continue_debate(state) == "Research Manager"


@pytest.mark.unit
def test_debate_alternates_speakers():
    """Bull spoke last, Bear should go next."""
    cl = ConditionalLogic(max_debate_rounds=2)
    state = _make_state(has_tool_calls=False, debate_count=1, last_speaker="Bull")
    assert cl.should_continue_debate(state) == "Bear Researcher"


@pytest.mark.unit
def test_risk_analysis_terminates_at_max_rounds():
    """Risk debate routes to Portfolio Manager when round limit hit."""
    cl = ConditionalLogic(max_risk_discuss_rounds=1)
    state = _make_state(has_tool_calls=False, debate_count=3, last_speaker="Aggressive")
    assert cl.should_continue_risk_analysis(state) == "Portfolio Manager"


@pytest.mark.unit
def test_routing_is_mode_agnostic():
    """
    The conditional logic does NOT branch on instrument_type. Routing is
    the same for stock and polymarket modes. This locks in the design
    decision that prompts (not graph routing) carry the mode-specific
    behavior.
    """
    cl = ConditionalLogic()
    stock_state = _make_state(has_tool_calls=True)
    stock_state["instrument_type"] = "stock"
    pm_state = _make_state(has_tool_calls=True)
    pm_state["instrument_type"] = "polymarket"
    assert cl.should_continue_market(stock_state) == cl.should_continue_market(pm_state)
    assert cl.should_continue_news(stock_state) == cl.should_continue_news(pm_state)
