def test_agent_state_declares_canonical_regime():
    from tradingagents.agents.utils.agent_states import AgentState

    assert "canonical_regime" in AgentState.__annotations__
