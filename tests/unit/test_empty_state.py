"""Tests for empty/error state handling across agents.

Validates that agents handle missing/empty/error data gracefully without
hallucinating — particularly the NO-DATA guard in MacroSummaryAgent that
must short-circuit before invoking the LLM.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.portfolio.macro_summary_agent import (
    create_macro_summary_agent,
)


class TestEmptyStateGuards:
    """Validate that agents handle missing/empty data gracefully without hallucinating."""

    def test_macro_agent_empty_dict(self):
        """Empty scan_summary dict triggers NO DATA sentinel; LLM not invoked."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        result = agent({"scan_summary": {}, "messages": [], "analysis_date": ""})
        assert result["macro_brief"] == "NO DATA AVAILABLE - ABORT MACRO"
        # LLM must NOT be invoked
        mock_llm.invoke.assert_not_called()
        mock_llm.with_structured_output.assert_not_called()

    def test_macro_agent_none_scan(self):
        """None scan_summary triggers NO DATA sentinel."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        result = agent({"scan_summary": None, "messages": [], "analysis_date": ""})
        assert result["macro_brief"] == "NO DATA AVAILABLE - ABORT MACRO"

    def test_macro_agent_error_key(self):
        """scan_summary with 'error' key triggers NO DATA sentinel."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        result = agent({
            "scan_summary": {"error": "rate limit exceeded"},
            "messages": [],
            "analysis_date": "",
        })
        assert result["macro_brief"] == "NO DATA AVAILABLE - ABORT MACRO"

    def test_macro_agent_missing_scan_key(self):
        """State dict with no scan_summary key at all triggers NO DATA sentinel.

        state.get('scan_summary') returns None → should trigger guard.
        """
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        result = agent({"messages": [], "analysis_date": ""})
        assert result["macro_brief"] == "NO DATA AVAILABLE - ABORT MACRO"

    def test_macro_agent_no_data_path_does_not_invoke_llm(self):
        """All NO-DATA guard paths must leave the LLM untouched."""
        no_data_states = [
            {"scan_summary": {}, "messages": [], "analysis_date": ""},
            {"scan_summary": None, "messages": [], "analysis_date": ""},
            {"scan_summary": {"error": "timeout"}, "messages": [], "analysis_date": ""},
            {"messages": [], "analysis_date": ""},
        ]
        for state in no_data_states:
            mock_llm = MagicMock()
            agent = create_macro_summary_agent(mock_llm)
            agent(state)
            mock_llm.invoke.assert_not_called()
            mock_llm.__ror__.assert_not_called()

    def test_macro_agent_no_data_returns_correct_sender(self):
        """Sender is always 'macro_summary_agent' even on the NO-DATA path."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        result = agent({"scan_summary": {}, "messages": [], "analysis_date": ""})
        assert result["sender"] == "macro_summary_agent"

    def test_macro_agent_no_data_macro_memory_context_empty_string(self):
        """macro_memory_context is an empty string on the NO-DATA path."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        result = agent({"scan_summary": {}, "messages": [], "analysis_date": ""})
        assert result["macro_memory_context"] == ""

    def test_macro_agent_error_only_key_triggers_sentinel(self):
        """scan_summary that ONLY contains 'error' (no other keys) triggers guard."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        result = agent({
            "scan_summary": {"error": "vendor offline"},
            "messages": [],
            "analysis_date": "2026-03-26",
        })
        assert result["macro_brief"] == "NO DATA AVAILABLE - ABORT MACRO"

    def test_macro_agent_scan_with_data_and_error_key_proceeds(self):
        """scan_summary with real data AND an 'error' key is NOT discarded.

        Only scan_summary whose *only* key is 'error' triggers the guard.
        Partial failures with usable data should still be compressed.
        """
        from langchain_core.messages import AIMessage
        from langchain_core.runnables import RunnableLambda

        mock_llm = RunnableLambda(lambda _: AIMessage(content="MACRO REGIME: neutral\nPartial data processed"))
        agent = create_macro_summary_agent(mock_llm)
        result = agent({
            "scan_summary": {
                "executive_summary": "Partial data",
                "error": "partial failure",
            },
            "messages": [],
            "analysis_date": "2026-03-26",
        })
        # Should NOT be sentinel — the LLM was invoked
        assert result["macro_brief"] != "NO DATA AVAILABLE - ABORT MACRO"
