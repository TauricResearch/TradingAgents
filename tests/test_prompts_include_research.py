"""Verify each of bull/bear/research_manager/trader propagates user_research_report
into the prompt that gets sent to the LLM."""

from unittest.mock import MagicMock


def _fake_state(**overrides):
    base = {
        "company_of_interest": "AAPL",
        "trade_date": "2026-05-06",
        "market_report": "M",
        "sentiment_report": "S",
        "news_report": "N",
        "fundamentals_report": "F",
        "user_research_report": "## Goldman bullish\nUNIQUE_MARKER_42",
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
            "judge_decision": "",
        },
        "investment_plan": "BUY",
    }
    base.update(overrides)
    return base


def _capturing_llm():
    """Returns (llm, captured_prompts: list[str])."""
    llm = MagicMock()
    captured = []
    def _inv(prompt):
        if isinstance(prompt, list):
            content = "\n".join(m.get("content", "") for m in prompt if isinstance(m, dict))
        else:
            content = str(prompt)
        captured.append(content)
        return MagicMock(content="ok")
    llm.invoke.side_effect = _inv
    llm.with_structured_output = MagicMock(return_value=llm)
    return llm, captured


def test_bull_researcher_includes_user_research():
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
    llm, captured = _capturing_llm()
    node = create_bull_researcher(llm)
    node(_fake_state())
    assert any("UNIQUE_MARKER_42" in c for c in captured), captured


def test_bear_researcher_includes_user_research():
    from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
    llm, captured = _capturing_llm()
    node = create_bear_researcher(llm)
    node(_fake_state())
    assert any("UNIQUE_MARKER_42" in c for c in captured), captured


def test_research_manager_includes_user_research():
    from tradingagents.agents.managers.research_manager import create_research_manager
    llm, captured = _capturing_llm()
    node = create_research_manager(llm)
    try:
        node(_fake_state())
    except Exception:
        pass  # structured output path may swallow; we only care about prompt capture
    assert any("UNIQUE_MARKER_42" in c for c in captured), captured


def test_trader_includes_user_research():
    from tradingagents.agents.trader.trader import create_trader
    llm, captured = _capturing_llm()
    node = create_trader(llm)
    try:
        node(_fake_state())
    except Exception:
        pass
    assert any("UNIQUE_MARKER_42" in c for c in captured), captured


def test_empty_research_does_not_inject_block():
    """When user_research_report == "", prompts must not contain the framing line."""
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
    llm, captured = _capturing_llm()
    node = create_bull_researcher(llm)
    node(_fake_state(user_research_report=""))
    assert not any("User-uploaded research" in c for c in captured), captured
