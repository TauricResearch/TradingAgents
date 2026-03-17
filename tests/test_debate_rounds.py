"""Tests for agentic debate round configuration and conditional logic."""

import pytest
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.agents.utils.agent_states import InvestDebateState, RiskDebateState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_invest_state(count: int, current_response: str = "Bull: some argument") -> dict:
    return {
        "investment_debate_state": InvestDebateState(
            bull_history="",
            bear_history="",
            history="",
            current_response=current_response,
            judge_decision="",
            count=count,
        )
    }


def _make_risk_state(count: int, latest_speaker: str = "Aggressive") -> dict:
    return {
        "risk_debate_state": RiskDebateState(
            aggressive_history="",
            conservative_history="",
            neutral_history="",
            history="",
            latest_speaker=latest_speaker,
            current_aggressive_response="",
            current_conservative_response="",
            current_neutral_response="",
            judge_decision="",
            count=count,
        )
    }


# ---------------------------------------------------------------------------
# ConditionalLogic default initialization
# ---------------------------------------------------------------------------

class TestConditionalLogicDefaults:
    def test_default_max_debate_rounds(self):
        cl = ConditionalLogic()
        assert cl.max_debate_rounds == 1

    def test_default_max_risk_discuss_rounds(self):
        cl = ConditionalLogic()
        assert cl.max_risk_discuss_rounds == 1


# ---------------------------------------------------------------------------
# Investment debate routing — 2 rounds
# ---------------------------------------------------------------------------

class TestInvestDebateRounds2:
    def setup_method(self):
        self.cl = ConditionalLogic(max_debate_rounds=2)

    def test_bull_speaks_first(self):
        # count=0, current_response starts with "Bull" → go to Bear
        state = _make_invest_state(count=0, current_response="Bull: bullish case")
        result = self.cl.should_continue_debate(state)
        assert result == "Bear Researcher"

    def test_bear_speaks_second(self):
        # count=1, current_response does NOT start with "Bull" → go to Bull
        state = _make_invest_state(count=1, current_response="Bear: bearish case")
        result = self.cl.should_continue_debate(state)
        assert result == "Bull Researcher"

    def test_bull_speaks_third(self):
        # count=2, threshold=2*2=4, not reached; Bull spoke last so Bear goes
        state = _make_invest_state(count=2, current_response="Bull: second argument")
        result = self.cl.should_continue_debate(state)
        assert result == "Bear Researcher"

    def test_bear_speaks_fourth(self):
        # count=3, threshold=4, not reached; Bear spoke last so Bull goes
        state = _make_invest_state(count=3, current_response="Bear: second rebuttal")
        result = self.cl.should_continue_debate(state)
        assert result == "Bull Researcher"

    def test_routes_to_manager_at_threshold(self):
        # count=4 == 2*2=4 → route to Research Manager
        state = _make_invest_state(count=4, current_response="Bull: final word")
        result = self.cl.should_continue_debate(state)
        assert result == "Research Manager"

    def test_routes_to_manager_above_threshold(self):
        # count=6 > threshold → still route to Research Manager
        state = _make_invest_state(count=6, current_response="Bull: anything")
        result = self.cl.should_continue_debate(state)
        assert result == "Research Manager"


# ---------------------------------------------------------------------------
# Investment debate routing — 3 rounds
# ---------------------------------------------------------------------------

class TestInvestDebateRounds3:
    def setup_method(self):
        self.cl = ConditionalLogic(max_debate_rounds=3)

    def test_threshold_is_6(self):
        # count=5, threshold=3*2=6, not reached
        state = _make_invest_state(count=5, current_response="Bull: fifth turn")
        result = self.cl.should_continue_debate(state)
        assert result == "Bear Researcher"

    def test_routes_to_manager_at_6(self):
        state = _make_invest_state(count=6, current_response="Bull: sixth turn")
        result = self.cl.should_continue_debate(state)
        assert result == "Research Manager"


# ---------------------------------------------------------------------------
# Risk debate routing — 2 rounds
# ---------------------------------------------------------------------------

class TestRiskDebateRounds2:
    def setup_method(self):
        self.cl = ConditionalLogic(max_risk_discuss_rounds=2)

    def test_aggressive_goes_to_conservative(self):
        state = _make_risk_state(count=0, latest_speaker="Aggressive")
        result = self.cl.should_continue_risk_analysis(state)
        assert result == "Conservative Analyst"

    def test_conservative_goes_to_neutral(self):
        state = _make_risk_state(count=1, latest_speaker="Conservative")
        result = self.cl.should_continue_risk_analysis(state)
        assert result == "Neutral Analyst"

    def test_neutral_goes_to_aggressive(self):
        state = _make_risk_state(count=2, latest_speaker="Neutral")
        result = self.cl.should_continue_risk_analysis(state)
        assert result == "Aggressive Analyst"

    def test_threshold_at_6(self):
        # count=6 == 3*2=6 → route to Risk Judge
        state = _make_risk_state(count=6, latest_speaker="Aggressive")
        result = self.cl.should_continue_risk_analysis(state)
        assert result == "Risk Judge"

    def test_continues_at_count_5(self):
        state = _make_risk_state(count=5, latest_speaker="Aggressive")
        result = self.cl.should_continue_risk_analysis(state)
        assert result == "Conservative Analyst"


# ---------------------------------------------------------------------------
# Config wiring — verify TradingAgentsGraph passes config to ConditionalLogic
# ---------------------------------------------------------------------------

class TestConfigWiring:
    def test_trading_graph_wires_debate_rounds(self):
        """ConditionalLogic should use config values, not hardcoded defaults."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=2)
        assert cl.max_debate_rounds == 2
        assert cl.max_risk_discuss_rounds == 2

    def test_default_config_has_updated_values(self):
        """Default config should now ship with max_debate_rounds=2."""
        from tradingagents.default_config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["max_debate_rounds"] == 2
        assert DEFAULT_CONFIG["max_risk_discuss_rounds"] == 2
