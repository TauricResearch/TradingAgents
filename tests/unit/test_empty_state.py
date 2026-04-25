"""Tests for empty/error state handling across agents.

Validates that agents handle missing/empty/error data gracefully without
hallucinating — particularly the NO-DATA guard in MacroSummaryAgent that
must short-circuit before invoking the LLM.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from tradingagents.agents.portfolio.macro_summary_agent import (
    create_macro_summary_agent,
)


class TestEmptyStateGuards:
    """Validate that agents handle missing/empty data gracefully without hallucinating."""

    def test_macro_agent_empty_dict(self):
        """Empty scan_summary dict raises RuntimeError; LLM not invoked."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        with pytest.raises(RuntimeError):
            agent({"scan_summary": {}, "messages": [], "analysis_date": ""})
        mock_llm.invoke.assert_not_called()
        mock_llm.with_structured_output.assert_not_called()

    def test_macro_agent_none_scan(self):
        """None scan_summary raises RuntimeError."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        with pytest.raises(RuntimeError):
            agent({"scan_summary": None, "messages": [], "analysis_date": ""})

    def test_macro_agent_error_key(self):
        """scan_summary with 'error' key raises RuntimeError."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        with pytest.raises(RuntimeError):
            agent(
                {
                    "scan_summary": {"error": "rate limit exceeded"},
                    "messages": [],
                    "analysis_date": "",
                }
            )

    def test_macro_agent_missing_scan_key(self):
        """State dict with no scan_summary key at all raises RuntimeError."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        with pytest.raises(RuntimeError):
            agent({"messages": [], "analysis_date": ""})

    def test_macro_agent_no_data_path_does_not_invoke_llm(self):
        """All NO-DATA guard paths must raise RuntimeError and leave the LLM untouched."""
        no_data_states = [
            {"scan_summary": {}, "messages": [], "analysis_date": ""},
            {"scan_summary": None, "messages": [], "analysis_date": ""},
            {"scan_summary": {"error": "timeout"}, "messages": [], "analysis_date": ""},
            {"messages": [], "analysis_date": ""},
        ]
        for state in no_data_states:
            mock_llm = MagicMock()
            agent = create_macro_summary_agent(mock_llm)
            with pytest.raises(RuntimeError):
                agent(state)
            mock_llm.invoke.assert_not_called()
            mock_llm.__ror__.assert_not_called()

    def test_macro_agent_no_data_raises_on_missing_scan_summary(self):
        """Missing scan_summary raises RuntimeError."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        with pytest.raises(RuntimeError):
            agent({"scan_summary": {}, "messages": [], "analysis_date": ""})

    def test_macro_agent_error_only_key_raises(self):
        """scan_summary that ONLY contains 'error' (no other keys) raises RuntimeError."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        with pytest.raises(RuntimeError):
            agent(
                {
                    "scan_summary": {"error": "vendor offline"},
                    "messages": [],
                    "analysis_date": "2026-03-26",
                }
            )

    def test_macro_agent_scan_with_data_and_error_key_proceeds(self):
        """scan_summary with real data AND an 'error' key is NOT discarded.

        Only scan_summary whose *only* key is 'error' triggers the guard.
        Partial failures with usable data should still be compressed.
        """
        from langchain_core.messages import AIMessage
        from langchain_core.runnables import RunnableLambda

        mock_llm = RunnableLambda(
            lambda _: AIMessage(content="MACRO REGIME: neutral\nPartial data processed")
        )
        agent = create_macro_summary_agent(mock_llm)
        result = agent(
            {
                "scan_summary": {
                    "executive_summary": "Partial data",
                    "error": "partial failure",
                },
                "messages": [],
                "analysis_date": "2026-03-26",
            }
        )
        # Should NOT be sentinel — the LLM was invoked
        assert result["macro_brief"] != "NO DATA AVAILABLE - ABORT MACRO"
