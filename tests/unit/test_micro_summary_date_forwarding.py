"""Unit tests for micro_summary_agent date forwarding.

Validates: Requirements 3.1, 3.2

- micro_summary_agent raises RuntimeError when analysis_date is missing
- micro_summary_agent passes analysis_date as as_of_date to build_context()
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.agents.portfolio.micro_summary_agent import create_micro_summary_agent


@pytest.fixture
def mock_llm():
    """Create a mock LLM that returns a valid micro brief."""
    llm = MagicMock()
    response = MagicMock()
    response.content = (
        "HOLDINGS TABLE:\n"
        "| TICKER | ACTION | KEY NUMBER | FLAG | MEMORY |\n"
        "|--------|--------|------------|------|--------|\n"
        "| AAPL | HOLD | rating:BUY | - | no memory |\n\n"
        "CANDIDATES TABLE:\n"
        "| TICKER | CONVICTION | THESIS ANGLE | KEY NUMBER | FLAG | MEMORY |\n"
        "|--------|------------|--------------|------------|------|--------|\n"
        "| MSFT | high | momentum | priority_score:85 | - | no memory |\n\n"
        "RED FLAGS: None\n"
        "GREEN FLAGS: AAPL momentum +5%\n"
    )
    llm.__or__ = MagicMock(return_value=MagicMock(invoke=MagicMock(return_value=response)))
    # For prompt | llm chain
    llm.invoke = MagicMock(return_value=response)
    return llm


@pytest.fixture
def mock_memory():
    """Create a mock ReflexionMemory."""
    memory = MagicMock()
    memory.build_context = MagicMock(return_value="No prior decisions recorded for TEST.")
    return memory


def test_raises_runtime_error_when_analysis_date_missing(mock_llm, mock_memory):
    """micro_summary_agent must raise RuntimeError when analysis_date is missing.

    Validates: Requirement 3.2
    """
    node = create_micro_summary_agent(mock_llm, micro_memory=mock_memory)

    state = {
        "analysis_date": "",  # empty = missing
        "holding_reviews": '{"AAPL": {"recommendation": "HOLD", "confidence": "high"}}',
        "prioritized_candidates": '[{"ticker": "MSFT", "conviction": "high", "thesis_angle": "momentum"}]',
        "ticker_analyses": {},
        "messages": [],
    }

    with pytest.raises(RuntimeError, match="missing analysis_date"):
        node(state)


def test_raises_runtime_error_when_analysis_date_none(mock_llm, mock_memory):
    """micro_summary_agent must raise RuntimeError when analysis_date is None.

    Validates: Requirement 3.2
    """
    node = create_micro_summary_agent(mock_llm, micro_memory=mock_memory)

    state = {
        "analysis_date": None,
        "holding_reviews": '{"AAPL": {"recommendation": "HOLD"}}',
        "prioritized_candidates": "[]",
        "ticker_analyses": {},
        "messages": [],
    }

    with pytest.raises(RuntimeError, match="missing analysis_date"):
        node(state)


def test_passes_analysis_date_as_as_of_date_to_build_context(mock_llm, mock_memory):
    """micro_summary_agent must pass analysis_date as as_of_date to build_context().

    Validates: Requirement 3.1
    """
    node = create_micro_summary_agent(mock_llm, micro_memory=mock_memory)

    state = {
        "analysis_date": "2026-03-20",
        "holding_reviews": '{"AAPL": {"recommendation": "HOLD", "confidence": "high"}}',
        "prioritized_candidates": '[{"ticker": "MSFT", "conviction": "high", "thesis_angle": "momentum"}]',
        "ticker_analyses": {},
        "messages": [],
    }

    # We need to patch the chain invocation to avoid LLM call
    with patch(
        "tradingagents.agents.portfolio.micro_summary_agent.ChatPromptTemplate"
    ) as mock_prompt_cls:
        mock_prompt = MagicMock()
        mock_prompt.partial.return_value = mock_prompt
        mock_prompt.__or__ = MagicMock(
            return_value=MagicMock(
                invoke=MagicMock(
                    return_value=MagicMock(content="HOLDINGS TABLE:\n| TICKER | ACTION |\nRED FLAGS: None\nGREEN FLAGS: None")
                )
            )
        )
        mock_prompt_cls.from_messages.return_value = mock_prompt

        node(state)

    # Verify build_context was called with as_of_date="2026-03-20" for each ticker
    calls = mock_memory.build_context.call_args_list
    assert len(calls) >= 1, "build_context should have been called at least once"

    for call in calls:
        # Check keyword argument as_of_date
        assert call.kwargs.get("as_of_date") == "2026-03-20", (
            f"Expected as_of_date='2026-03-20', got {call.kwargs}"
        )


def test_no_error_when_memory_is_none(mock_llm):
    """micro_summary_agent should not raise when micro_memory is None (memory skipped).

    Validates: graceful degradation when memory is not configured.
    """
    node = create_micro_summary_agent(mock_llm, micro_memory=None)

    state = {
        "analysis_date": "2026-03-20",
        "holding_reviews": '{"AAPL": {"recommendation": "HOLD"}}',
        "prioritized_candidates": "[]",
        "ticker_analyses": {},
        "messages": [],
    }

    # Should not raise — memory features are simply skipped
    with patch(
        "tradingagents.agents.portfolio.micro_summary_agent.ChatPromptTemplate"
    ) as mock_prompt_cls:
        mock_prompt = MagicMock()
        mock_prompt.partial.return_value = mock_prompt
        mock_prompt.__or__ = MagicMock(
            return_value=MagicMock(
                invoke=MagicMock(
                    return_value=MagicMock(content="HOLDINGS TABLE:\nRED FLAGS: None\nGREEN FLAGS: None")
                )
            )
        )
        mock_prompt_cls.from_messages.return_value = mock_prompt

        result = node(state)

    assert "micro_brief" in result
