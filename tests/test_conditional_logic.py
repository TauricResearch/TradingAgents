import pytest

from tradingagents.graph.conditional_logic import ConditionalLogic


def _state(investment_count=0, risk_count=0):
    return {
        "investment_debate_state": {
            "count": investment_count,
            "current_response": "unexpected speaker",
        },
        "risk_debate_state": {
            "count": risk_count,
            "latest_speaker": "unexpected speaker",
        },
    }


@pytest.mark.parametrize(
    ("method_name", "allowed_next_node"),
    [
        ("should_continue_after_bull_researcher", "Bear Researcher"),
        ("should_continue_after_bear_researcher", "Bull Researcher"),
    ],
)
def test_investment_debate_edges_only_return_mapped_nodes(method_name, allowed_next_node):
    logic = ConditionalLogic(max_debate_rounds=1)
    router = getattr(logic, method_name)

    assert router(_state(investment_count=0)) == allowed_next_node
    assert router(_state(investment_count=2)) == "Research Manager"


@pytest.mark.parametrize(
    ("method_name", "allowed_next_node"),
    [
        ("should_continue_after_aggressive_analyst", "Conservative Analyst"),
        ("should_continue_after_conservative_analyst", "Neutral Analyst"),
        ("should_continue_after_neutral_analyst", "Aggressive Analyst"),
    ],
)
def test_risk_debate_edges_only_return_mapped_nodes(method_name, allowed_next_node):
    logic = ConditionalLogic(max_risk_discuss_rounds=1)
    router = getattr(logic, method_name)

    assert router(_state(risk_count=0)) == allowed_next_node
    assert router(_state(risk_count=3)) == "Portfolio Manager"
