def test_agent_state_declares_canonical_regime():
    from tradingagents.agents.utils.agent_states import AgentState

    assert "canonical_regime" in AgentState.__annotations__


def test_market_analyst_prompt_includes_canonical_regime():
    """Confirm the prompt builder substitutes canonical regime when present."""
    from tradingagents.agents.analysts.market_analyst import _build_market_prompt

    state = {
        "company_of_interest": "QCOM",
        "trade_date": "2026-04-30",
        "canonical_regime": {
            "label": "RISK-ON",
            "score": 5,
            "brief": "RISK-ON (+5/6) suppressed VIX",
        },
    }
    prompt = _build_market_prompt(state)
    assert "RISK-ON" in prompt
    assert "+5/6" in prompt
    assert "infer the regime" not in prompt.lower()
