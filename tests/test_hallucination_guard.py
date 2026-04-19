"""Tests for memory hallucination guard across all five agents.

Verifies that:
- Memory section headers are ABSENT from prompts when memory is empty.
- Memory content IS injected when memory is populated.

No LLM API calls are made — llm.invoke() is mocked.
"""

from unittest.mock import MagicMock

from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.trader.trader import create_trader
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_state():
    return {
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
        "market_report": "market data",
        "sentiment_report": "sentiment data",
        "news_report": "news data",
        "fundamentals_report": "fundamentals data",
        "company_of_interest": "AAPL",
        "trade_date": "2024-01-15",
        "investment_plan": "buy AAPL",
        "trader_investment_plan": "",
        "risk_debate_state": {
            "history": "",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "judge_decision": "",
            "count": 0,
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
        },
    }


def _mock_llm():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="mocked response")
    return llm


def _empty_memory():
    m = MagicMock()
    m.get_memories.return_value = []
    return m


def _populated_memory(lesson="Past lesson: watch macro risk"):
    m = MagicMock()
    m.get_memories.return_value = [{"recommendation": lesson, "similarity_score": 0.9}]
    return m


# ---------------------------------------------------------------------------
# Bull Researcher
# ---------------------------------------------------------------------------

def test_bull_omits_memory_section_when_empty():
    """No reflections header or instruction when memory is empty."""
    llm = _mock_llm()
    node = create_bull_researcher(llm, _empty_memory())
    node(_make_state())

    prompt = llm.invoke.call_args[0][0]
    assert "Reflections from similar situations" not in prompt
    assert "address reflections" not in prompt.lower()
    assert "learn from lessons and mistakes" not in prompt.lower()


def test_bull_includes_memory_section_when_populated():
    """Lesson text appears in prompt when memory is populated."""
    llm = _mock_llm()
    node = create_bull_researcher(llm, _populated_memory("Reduce tech exposure on rate hikes"))
    node(_make_state())

    prompt = llm.invoke.call_args[0][0]
    assert "Reduce tech exposure on rate hikes" in prompt
    assert "Reflections from similar situations" in prompt


# ---------------------------------------------------------------------------
# Bear Researcher
# ---------------------------------------------------------------------------

def test_bear_omits_memory_section_when_empty():
    """No reflections header or instruction when memory is empty."""
    llm = _mock_llm()
    node = create_bear_researcher(llm, _empty_memory())
    node(_make_state())

    prompt = llm.invoke.call_args[0][0]
    assert "Reflections from similar situations" not in prompt
    assert "address reflections" not in prompt.lower()
    assert "learn from lessons and mistakes" not in prompt.lower()


def test_bear_includes_memory_section_when_populated():
    """Lesson text appears in prompt when memory is populated."""
    llm = _mock_llm()
    node = create_bear_researcher(llm, _populated_memory("Overestimated resilience in 2022"))
    node(_make_state())

    prompt = llm.invoke.call_args[0][0]
    assert "Overestimated resilience in 2022" in prompt
    assert "Reflections from similar situations" in prompt


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------

def test_trader_omits_reflection_clause_when_empty():
    """No reflection text or 'No past memories found.' in system message when empty."""
    llm = _mock_llm()
    node = create_trader(llm, _empty_memory())
    node(_make_state())

    messages = llm.invoke.call_args[0][0]
    system_content = messages[0]["content"]
    assert "No past memories found" not in system_content
    assert "Here are reflections" not in system_content
    assert "Apply lessons from past decisions" not in system_content


def test_trader_includes_reflection_clause_when_populated():
    """Lesson text appears in system message when memory is populated."""
    llm = _mock_llm()
    node = create_trader(llm, _populated_memory("Avoid chasing momentum tops"))
    node(_make_state())

    messages = llm.invoke.call_args[0][0]
    system_content = messages[0]["content"]
    assert "Avoid chasing momentum tops" in system_content
    assert "Apply lessons from past decisions" in system_content


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------

def test_research_manager_omits_memory_section_when_empty():
    """No past reflections header when memory is empty."""
    llm = _mock_llm()
    node = create_research_manager(llm, _empty_memory())
    node(_make_state())

    prompt = llm.invoke.call_args[0][0]
    assert "Here are your past reflections on mistakes" not in prompt
    assert "Take into account your past mistakes" not in prompt


def test_research_manager_includes_memory_section_when_populated():
    """Lesson text and header appear in prompt when memory is populated."""
    llm = _mock_llm()
    node = create_research_manager(llm, _populated_memory("Missed earnings surprise signal"))
    node(_make_state())

    prompt = llm.invoke.call_args[0][0]
    assert "Missed earnings surprise signal" in prompt
    assert "Here are your past reflections on mistakes" in prompt


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------

def test_portfolio_manager_omits_lessons_line_when_empty():
    """No 'Lessons from past decisions' line when memory is empty."""
    llm = _mock_llm()
    node = create_portfolio_manager(llm, _empty_memory())
    node(_make_state())

    prompt = llm.invoke.call_args[0][0]
    assert "Lessons from past decisions" not in prompt


def test_portfolio_manager_includes_lessons_line_when_populated():
    """Lesson text and label appear in prompt when memory is populated."""
    llm = _mock_llm()
    node = create_portfolio_manager(llm, _populated_memory("Size down in low-liquidity names"))
    node(_make_state())

    prompt = llm.invoke.call_args[0][0]
    assert "Size down in low-liquidity names" in prompt
    assert "Lessons from past decisions" in prompt
