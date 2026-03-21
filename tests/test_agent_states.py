"""Tests for updated agent state definitions."""


def test_invest_debate_state_has_timing_fields():
    from tradingagents.agents.utils.agent_states import InvestDebateState
    keys = InvestDebateState.__annotations__
    assert "yes_history" in keys
    assert "no_history" in keys
    assert "timing_history" in keys
    assert "latest_speaker" in keys
    assert "current_yes_response" in keys
    assert "current_no_response" in keys
    assert "current_timing_response" in keys
    assert "bull_history" not in keys
    assert "bear_history" not in keys


def test_agent_state_has_polymarket_fields():
    from tradingagents.agents.utils.agent_states import AgentState
    keys = AgentState.__annotations__
    assert "event_id" in keys
    assert "event_question" in keys
    assert "odds_report" in keys
    assert "event_report" in keys
    assert "trader_plan" in keys
    assert "final_decision" in keys
    assert "company_of_interest" not in keys
    assert "market_report" not in keys
    assert "fundamentals_report" not in keys
    assert "trader_investment_plan" not in keys
    assert "final_trade_decision" not in keys


def test_risk_debate_state_unchanged():
    from tradingagents.agents.utils.agent_states import RiskDebateState
    keys = RiskDebateState.__annotations__
    assert "aggressive_history" in keys
    assert "conservative_history" in keys
    assert "neutral_history" in keys
    assert "latest_speaker" in keys
