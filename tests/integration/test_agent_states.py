import pytest
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


class TestInvestDebateState:
    def test_create_empty_state(self):
        state = InvestDebateState(
            bull_history="",
            bear_history="",
            history="",
            current_response="",
            judge_decision="",
            count=0,
        )
        assert state["count"] == 0
        assert state["history"] == ""

    def test_create_state_with_history(self):
        state = InvestDebateState(
            bull_history="Bull argues for buying",
            bear_history="Bear argues for selling",
            history="Bull: buy\nBear: sell",
            current_response="Bull: I maintain my position",
            judge_decision="",
            count=2,
        )
        assert state["count"] == 2
        assert "Bull" in state["bull_history"]
        assert "Bear" in state["bear_history"]

    def test_state_as_dict(self):
        state = InvestDebateState(
            bull_history="test",
            bear_history="test",
            history="test",
            current_response="test",
            judge_decision="BUY",
            count=1,
        )
        assert isinstance(state, dict)
        assert state["judge_decision"] == "BUY"


class TestRiskDebateState:
    def test_create_empty_state(self):
        state = RiskDebateState(
            risky_history="",
            safe_history="",
            neutral_history="",
            history="",
            latest_speaker="",
            current_risky_response="",
            current_safe_response="",
            current_neutral_response="",
            judge_decision="",
            count=0,
        )
        assert state["count"] == 0
        assert state["latest_speaker"] == ""

    def test_create_state_with_speakers(self):
        state = RiskDebateState(
            risky_history="Risky: Go all in!",
            safe_history="Safe: Be cautious",
            neutral_history="Neutral: Consider both",
            history="Discussion ongoing",
            latest_speaker="Risky Analyst",
            current_risky_response="Go all in!",
            current_safe_response="",
            current_neutral_response="",
            judge_decision="",
            count=1,
        )
        assert state["latest_speaker"] == "Risky Analyst"
        assert "Go all in" in state["risky_history"]

    def test_state_tracks_all_speakers(self):
        state = RiskDebateState(
            risky_history="Risky view",
            safe_history="Safe view",
            neutral_history="Neutral view",
            history="Full debate",
            latest_speaker="Neutral Analyst",
            current_risky_response="risky",
            current_safe_response="safe",
            current_neutral_response="neutral",
            judge_decision="APPROVED",
            count=3,
        )
        assert state["count"] == 3
        assert state["judge_decision"] == "APPROVED"


class TestAgentStateStructure:
    def test_agent_state_has_required_fields(self):
        required_fields = [
            "company_of_interest",
            "trade_date",
            "sender",
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_debate_state",
            "investment_plan",
            "trader_investment_plan",
            "risk_debate_state",
            "final_trade_decision",
        ]

        annotations = AgentState.__annotations__
        for field in required_fields:
            assert field in annotations, f"Missing field: {field}"
