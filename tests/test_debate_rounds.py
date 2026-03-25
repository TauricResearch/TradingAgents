from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.conditional_logic import ConditionalLogic


def _make_invest_state(count: int, current_response: str = "Bull: argument") -> dict:
    return {
        "investment_debate_state": {
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "current_response": current_response,
            "judge_decision": "",
            "count": count,
        }
    }


def _make_risk_state(count: int, latest_speaker: str = "Aggressive") -> dict:
    return {
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "latest_speaker": latest_speaker,
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": count,
        }
    }


def test_conditional_logic_defaults_are_2():
    logic = ConditionalLogic()

    assert logic.max_debate_rounds == 2
    assert logic.max_risk_discuss_rounds == 2


def test_investment_debate_threshold_uses_max_debate_rounds():
    logic = ConditionalLogic(max_debate_rounds=2)

    assert logic.should_continue_debate(_make_invest_state(3, "Bear: rebuttal")) == (
        "Bull Researcher"
    )
    assert logic.should_continue_debate(_make_invest_state(4, "Bull: final")) == (
        "Research Manager"
    )


def test_risk_debate_threshold_uses_max_risk_discuss_rounds():
    logic = ConditionalLogic(max_risk_discuss_rounds=2)

    assert logic.should_continue_risk_analysis(
        _make_risk_state(5, latest_speaker="Neutral")
    ) == "Aggressive Analyst"
    assert logic.should_continue_risk_analysis(
        _make_risk_state(6, latest_speaker="Aggressive")
    ) == "Portfolio Manager"


def test_default_config_round_defaults_are_2():
    assert DEFAULT_CONFIG["max_debate_rounds"] == 2
    assert DEFAULT_CONFIG["max_risk_discuss_rounds"] == 2
