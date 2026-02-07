"""Tests for the risk manager node (tradingagents/agents/managers/risk_manager.py).

Verifies the copy-paste bug fix: the risk manager must use fundamentals_report
(not a duplicate of news_report) when building its situation string.
"""

from unittest.mock import MagicMock

from tradingagents.agents.managers.risk_manager import create_risk_manager


def _make_state(news="news-text", fundamentals="fundamentals-text"):
    """Return a minimal state dict suitable for risk_manager_node."""
    return {
        "company_of_interest": "AAPL",
        "risk_debate_state": {
            "history": "debate history",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 0,
        },
        "market_report": "market-text",
        "news_report": news,
        "fundamentals_report": fundamentals,
        "sentiment_report": "sentiment-text",
        "investment_plan": "plan-text",
    }


def test_risk_manager_reads_fundamentals_report_not_news():
    """The curr_situation string must contain the fundamentals_report value,
    not a second copy of news_report (the bug that was fixed at line 14)."""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="BUY")

    memory = MagicMock()
    memory.get_memories.return_value = []

    node = create_risk_manager(llm, memory)
    state = _make_state(news="NEWS_UNIQUE", fundamentals="FUNDAMENTALS_UNIQUE")
    node(state)

    # The LLM should have been called once; grab the prompt
    llm.invoke.assert_called_once()
    prompt = llm.invoke.call_args[0][0]

    # curr_situation is passed to memory.get_memories, not directly to LLM,
    # but the fundamentals text appears in the prompt via the debate history context.
    # More directly: memory.get_memories receives curr_situation as its first arg.
    memory.get_memories.assert_called_once()
    situation_arg = memory.get_memories.call_args[0][0]

    assert "FUNDAMENTALS_UNIQUE" in situation_arg, (
        "fundamentals_report should appear in the situation string"
    )
    # Also verify news is present (it should be there once, not duplicated for fundamentals)
    assert "NEWS_UNIQUE" in situation_arg, (
        "news_report should appear in the situation string"
    )


def test_risk_manager_returns_expected_state_keys():
    """The node must return a dict with 'risk_debate_state' and 'final_trade_decision'."""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="HOLD")

    memory = MagicMock()
    memory.get_memories.return_value = []

    node = create_risk_manager(llm, memory)
    result = node(_make_state())

    assert "risk_debate_state" in result
    assert "final_trade_decision" in result
    assert result["final_trade_decision"] == "HOLD"
