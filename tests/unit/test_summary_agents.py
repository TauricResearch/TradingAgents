"""Tests for Macro_Summary_Agent and Micro_Summary_Agent.

Strategy:
- Empty/error state paths skip the LLM entirely — test those directly.
- LLM-invoked paths require the mock to be a proper LangChain Runnable so that
  ``prompt | llm`` creates a working RunnableSequence.  LangChain's pipe operator
  calls through its own Runnable machinery — a plain MagicMock is NOT invoked via
  Python's raw ``__call__``.  We use ``RunnableLambda`` to wrap a lambda that
  returns a fixed AIMessage, making it fully compatible with the chain.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.portfolio.macro_summary_agent import (
    create_macro_summary_agent,
)
from tradingagents.agents.portfolio.micro_summary_agent import (
    create_micro_summary_agent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runnable_llm(content: str = "MACRO REGIME: risk-off\nKEY NUMBERS: VIX=25"):
    """Build a LangChain-compatible LLM stub via RunnableLambda.

    ``ChatPromptTemplate | llm`` creates a ``RunnableSequence``.  LangChain
    dispatches through its own Runnable protocol — the LLM must implement
    ``.invoke()`` as a Runnable, not just as a Python callable.
    ``RunnableLambda`` satisfies that contract.

    Returns:
        A ``RunnableLambda`` that always returns ``AIMessage(content=content)``.
    """
    ai_msg = AIMessage(content=content)
    return RunnableLambda(lambda _: ai_msg)


# Keep backward-compatible alias used by some tests that destructure a tuple
def _make_chain_mock(content: str = "MACRO REGIME: risk-off\nKEY NUMBERS: VIX=25"):
    """Return (llm_runnable, None) — second element kept for API compatibility."""
    return _make_runnable_llm(content), None


# ---------------------------------------------------------------------------
# MacroSummaryAgent — NO-DATA guard paths (LLM never called)
# ---------------------------------------------------------------------------


class TestMacroSummaryAgentNoDataGuard:
    """Verify the abort-early guard fires and LLM is not invoked."""

    def test_empty_scan_summary_returns_sentinel(self):
        """Empty scan_summary dict triggers NO DATA sentinel without LLM call."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        state = {"scan_summary": {}, "messages": [], "analysis_date": "2026-03-26"}
        result = agent(state)
        assert result["macro_brief"] == "NO DATA AVAILABLE - ABORT MACRO"
        mock_llm.invoke.assert_not_called()

    def test_none_scan_summary_returns_sentinel(self):
        """None scan_summary triggers NO DATA sentinel."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        state = {"scan_summary": None, "messages": [], "analysis_date": "2026-03-26"}
        result = agent(state)
        assert result["macro_brief"] == "NO DATA AVAILABLE - ABORT MACRO"

    def test_error_key_in_scan_returns_sentinel(self):
        """scan_summary with 'error' key triggers NO DATA sentinel."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        state = {
            "scan_summary": {"error": "vendor timeout"},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        result = agent(state)
        assert result["macro_brief"] == "NO DATA AVAILABLE - ABORT MACRO"

    def test_missing_scan_key_returns_sentinel(self):
        """State dict with no scan_summary key at all triggers NO DATA sentinel."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        result = agent({"messages": [], "analysis_date": "2026-03-26"})
        assert result["macro_brief"] == "NO DATA AVAILABLE - ABORT MACRO"


# ---------------------------------------------------------------------------
# MacroSummaryAgent — required state keys returned
# ---------------------------------------------------------------------------


class TestMacroSummaryAgentReturnShape:
    """Verify that every execution path returns the expected state keys."""

    def test_no_data_path_returns_required_keys(self):
        """NO-DATA guard path returns all required state keys."""
        agent = create_macro_summary_agent(MagicMock())
        result = agent({"scan_summary": {}, "messages": [], "analysis_date": ""})
        assert "macro_brief" in result
        assert "macro_memory_context" in result
        assert "sender" in result
        assert result["sender"] == "macro_summary_agent"

    def test_no_data_path_messages_is_list(self):
        """NO-DATA guard path returns messages as a list."""
        agent = create_macro_summary_agent(MagicMock())
        result = agent({"scan_summary": {}, "messages": [], "analysis_date": ""})
        assert isinstance(result["messages"], list)

    def test_llm_path_returns_required_keys(self):
        """LLM-invoked path returns all required state keys."""
        llm_mock, _ = _make_chain_mock("MACRO REGIME: neutral\nKEY NUMBERS: VIX=18")
        agent = create_macro_summary_agent(llm_mock)
        state = {
            "scan_summary": {"executive_summary": "Flat markets"},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        result = agent(state)
        assert "macro_brief" in result
        assert "macro_memory_context" in result
        assert "sender" in result
        assert result["sender"] == "macro_summary_agent"

    def test_llm_path_macro_brief_contains_llm_output(self):
        """macro_brief contains the LLM's returned content."""
        content = "MACRO REGIME: risk-on\nKEY NUMBERS: VIX=12"
        llm_mock, _ = _make_chain_mock(content)
        agent = create_macro_summary_agent(llm_mock)
        state = {
            "scan_summary": {"executive_summary": "Bull run"},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        result = agent(state)
        assert result["macro_brief"] == content


# ---------------------------------------------------------------------------
# MacroSummaryAgent — macro_memory integration
# ---------------------------------------------------------------------------


class TestMacroSummaryAgentMemory:
    """Verify macro_memory interaction without hitting MongoDB."""

    def test_no_memory_context_is_empty_string_on_no_data_path(self):
        """NO-DATA path returns empty string for macro_memory_context."""
        agent = create_macro_summary_agent(MagicMock())
        result = agent({"scan_summary": {}, "messages": [], "analysis_date": ""})
        assert result["macro_memory_context"] == ""

    def test_memory_context_injected_into_result(self, tmp_path):
        """When macro_memory is provided, macro_memory_context is populated."""
        from tradingagents.memory.macro_memory import MacroMemory

        mem = MacroMemory(fallback_path=tmp_path / "macro.json")
        mem.record_macro_state("2026-03-20", 25.0, "risk-off", "hawkish", ["rates"])

        llm_mock, _ = _make_chain_mock("MACRO REGIME: risk-off\nKEY NUMBERS: VIX=25")
        agent = create_macro_summary_agent(llm_mock, macro_memory=mem)
        state = {
            "scan_summary": {"executive_summary": "Risk-off conditions persist"},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        result = agent(state)
        # Past context built from the single recorded state should reference date
        assert "2026-03-20" in result["macro_memory_context"]


# ---------------------------------------------------------------------------
# MicroSummaryAgent — return shape
# ---------------------------------------------------------------------------


class TestMicroSummaryAgentReturnShape:
    """Verify the micro summary agent returns all required state keys."""

    def test_result_has_required_keys(self):
        """Agent returns all required state keys."""
        llm_mock, _ = _make_chain_mock("HOLDINGS TABLE:\n| TICKER | ACTION |")
        agent = create_micro_summary_agent(llm_mock)
        state = {
            "holding_reviews": "{}",
            "prioritized_candidates": "[]",
            "ticker_analyses": {},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        result = agent(state)
        assert "micro_brief" in result
        assert "micro_memory_context" in result
        assert "sender" in result
        assert result["sender"] == "micro_summary_agent"

    def test_micro_brief_contains_llm_output(self):
        """micro_brief contains the LLM's returned content."""
        content = "HOLDINGS TABLE:\n| AAPL | HOLD | 180 | green | good |"
        llm_mock, _ = _make_chain_mock(content)
        agent = create_micro_summary_agent(llm_mock)
        state = {
            "holding_reviews": '{"AAPL": {"recommendation": "HOLD", "confidence": "high"}}',
            "prioritized_candidates": "[]",
            "ticker_analyses": {},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        result = agent(state)
        assert result["micro_brief"] == content

    def test_sender_always_set(self):
        """sender key is always 'micro_summary_agent'."""
        llm_mock, _ = _make_chain_mock("brief output")
        agent = create_micro_summary_agent(llm_mock)
        state = {
            "holding_reviews": "{}",
            "prioritized_candidates": "[]",
            "ticker_analyses": {},
            "messages": [],
            "analysis_date": "",
        }
        result = agent(state)
        assert result["sender"] == "micro_summary_agent"


# ---------------------------------------------------------------------------
# MicroSummaryAgent — malformed input handling
# ---------------------------------------------------------------------------


class TestMicroSummaryAgentMalformedInput:
    """Verify that malformed JSON in state fields does not raise exceptions."""

    def test_invalid_holding_reviews_json_handled_gracefully(self):
        """Malformed JSON in holding_reviews does not raise."""
        llm_mock, _ = _make_chain_mock("brief")
        agent = create_micro_summary_agent(llm_mock)
        state = {
            "holding_reviews": "not valid json{{",
            "prioritized_candidates": "[]",
            "ticker_analyses": {},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        result = agent(state)
        assert "micro_brief" in result

    def test_invalid_candidates_json_handled_gracefully(self):
        """Malformed JSON in prioritized_candidates does not raise."""
        llm_mock, _ = _make_chain_mock("brief")
        agent = create_micro_summary_agent(llm_mock)
        state = {
            "holding_reviews": "{}",
            "prioritized_candidates": "also broken",
            "ticker_analyses": {},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        result = agent(state)
        assert "micro_brief" in result

    def test_both_inputs_malformed_does_not_raise(self):
        """Both holding_reviews and prioritized_candidates malformed — no raise."""
        llm_mock, _ = _make_chain_mock("brief")
        agent = create_micro_summary_agent(llm_mock)
        state = {
            "holding_reviews": "not valid json{{",
            "prioritized_candidates": "also broken",
            "ticker_analyses": {},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        result = agent(state)
        assert "micro_brief" in result

    def test_none_holding_reviews_handled(self):
        """None holding_reviews falls back gracefully."""
        llm_mock, _ = _make_chain_mock("brief")
        agent = create_micro_summary_agent(llm_mock)
        state = {
            "holding_reviews": None,
            "prioritized_candidates": None,
            "ticker_analyses": {},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        result = agent(state)
        assert "micro_brief" in result

    def test_missing_state_keys_handled(self):
        """Missing optional keys in state do not cause a KeyError."""
        llm_mock, _ = _make_chain_mock("brief")
        agent = create_micro_summary_agent(llm_mock)
        # Minimal state — only messages is truly required by the chain call
        state = {"messages": [], "analysis_date": "2026-03-26"}
        result = agent(state)
        assert "micro_brief" in result


# ---------------------------------------------------------------------------
# MicroSummaryAgent — memory integration
# ---------------------------------------------------------------------------


class TestMicroSummaryAgentMemory:
    """Verify micro_memory interaction."""

    def test_micro_memory_context_includes_ticker_history(self, tmp_path):
        """When micro_memory is provided with history, context string includes it."""
        from tradingagents.memory.reflexion import ReflexionMemory

        mem = ReflexionMemory(fallback_path=tmp_path / "reflexion.json")
        mem.record_decision("AAPL", "2026-03-20", "BUY", "Strong momentum", "high")

        llm_mock, _ = _make_chain_mock("brief")
        agent = create_micro_summary_agent(llm_mock, micro_memory=mem)
        state = {
            "holding_reviews": '{"AAPL": {"recommendation": "HOLD", "confidence": "high"}}',
            "prioritized_candidates": "[]",
            "ticker_analyses": {},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        result = agent(state)
        # micro_memory_context is JSON-serialised dict — AAPL should appear
        assert "AAPL" in result["micro_memory_context"]
