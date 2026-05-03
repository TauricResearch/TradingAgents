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


def test_engine_routes_canonical_regime_into_trading_state():
    """Initial trading state gets canonical regime from structured macro_scan_summary JSON."""
    import json

    from agent_os.backend.services.langgraph_engine import _build_trading_graph_initial_state

    macro_brief = json.dumps({"canonical_regime": {"label": "RISK-ON", "score": 5, "confidence": "high"}})
    state = _build_trading_graph_initial_state(
        ticker="QCOM",
        analysis_date="2026-05-01",
        run_id="run-123",
        macro_brief=macro_brief,
    )
    assert state["canonical_regime"]["label"] == "RISK-ON"
    assert state["canonical_regime"]["score"] == 5
