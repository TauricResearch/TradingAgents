from __future__ import annotations

import json
from unittest.mock import MagicMock, call

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.portfolio.holding_reviewer import create_holding_reviewer
from tradingagents.agents.portfolio.macro_summary_agent import (
    create_macro_summary_agent,
)
from tradingagents.agents.portfolio.micro_summary_agent import (
    _analysis_snapshot,
    create_micro_summary_agent,
)
from tradingagents.agents.portfolio.pm_decision_agent import (
    create_pm_decision_agent,
)

"""Tests for Macro_Summary_Agent and Micro_Summary_Agent.

Strategy:
- Empty/error state paths skip the LLM entirely — test those directly.
- LLM-invoked paths require the mock to be a proper LangChain Runnable so that
  ``prompt | llm`` creates a working RunnableSequence.  LangChain's pipe operator
  calls through its own Runnable machinery — a plain MagicMock is NOT invoked via
  Python's raw ``__call__``.  We use ``RunnableLambda`` to wrap a lambda that
  returns a fixed AIMessage, making it fully compatible with the chain.
"""

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


def _valid_pm_payload() -> dict:
    return {
        "macro_regime": "risk-off",
        "regime_alignment_note": "Elevated volatility favors selective exposure",
        "sells": [],
        "buys": [
            {
                "ticker": "AAPL",
                "shares": 2.0,
                "entry_price": 222.0,
                "limit_price": 224.0,
                "max_chase_price": 223.0,
                "order_type": "limit",
                "valid_as_of": "2026-03-30",
                "price_target": 240.0,
                "stop_loss": 205.0,
                "take_profit": 260.0,
                "sector": "Technology",
                "rationale": "Deep dive supports durable earnings quality",
                "thesis": "High-quality compounder",
                "macro_alignment": "Quality balance sheet fits the regime",
                "memory_note": "Held up well in prior slowdowns",
                "position_sizing_logic": "1% starter position",
            }
        ],
        "holds": [],
        "cash_reserve_pct": 0.1,
        "portfolio_thesis": "Selective quality exposure with cash buffer",
        "risk_summary": "Moderate portfolio risk",
        "forensic_report": {
            "regime_alignment": "Defensive growth is acceptable",
            "key_risks": ["multiple compression"],
            "decision_confidence": "medium",
            "position_sizing_rationale": "Keep exposure below hard caps",
        },
    }


# ---------------------------------------------------------------------------
# MacroSummaryAgent — NO-DATA guard paths (LLM never called)
# ---------------------------------------------------------------------------


class TestMacroSummaryAgentNoDataGuard:
    """Verify the abort-early guard fires and LLM is not invoked."""

    def test_empty_scan_summary_returns_sentinel(self):
        """Empty scan_summary dict raises RuntimeError without LLM call."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        state = {"scan_summary": {}, "messages": [], "analysis_date": "2026-03-26"}
        with pytest.raises(RuntimeError):
            agent(state)
        mock_llm.invoke.assert_not_called()

    def test_none_scan_summary_returns_sentinel(self):
        """None scan_summary raises RuntimeError."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        state = {"scan_summary": None, "messages": [], "analysis_date": "2026-03-26"}
        with pytest.raises(RuntimeError):
            agent(state)

    def test_error_key_in_scan_returns_sentinel(self):
        """scan_summary with 'error' key raises RuntimeError."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        state = {
            "scan_summary": {"error": "vendor timeout"},
            "messages": [],
            "analysis_date": "2026-03-26",
        }
        with pytest.raises(RuntimeError):
            agent(state)
        mock_llm.invoke.assert_not_called()

    def test_missing_scan_key_returns_sentinel(self):
        """State dict with no scan_summary key at all raises RuntimeError."""
        mock_llm = MagicMock()
        agent = create_macro_summary_agent(mock_llm)
        with pytest.raises(RuntimeError):
            agent({"messages": [], "analysis_date": "2026-03-26"})


# ---------------------------------------------------------------------------
# MacroSummaryAgent — required state keys returned
# ---------------------------------------------------------------------------


class TestMacroSummaryAgentReturnShape:
    """Verify that every execution path returns the expected state keys."""

    def test_no_data_path_returns_required_keys(self):
        """NO-DATA guard path now raises RuntimeError."""
        agent = create_macro_summary_agent(MagicMock())
        with pytest.raises(RuntimeError):
            agent({"scan_summary": {}, "messages": [], "analysis_date": ""})

    def test_no_data_path_messages_is_list(self):
        """NO-DATA guard path raises RuntimeError (no return value to inspect)."""
        agent = create_macro_summary_agent(MagicMock())
        with pytest.raises(RuntimeError):
            agent({"scan_summary": {}, "messages": [], "analysis_date": ""})

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

    def test_llm_path_empty_output_raises_runtime_error(self):
        """Empty LLM output raises instead of returning an empty macro brief."""
        llm_mock, _ = _make_chain_mock("")
        agent = create_macro_summary_agent(llm_mock)
        state = {
            "scan_summary": {"executive_summary": "Flat markets"},
            "messages": [],
            "analysis_date": "2026-03-26",
        }

        with pytest.raises(RuntimeError, match="macro_summary_agent.*empty"):
            agent(state)

    def test_macro_prompt_includes_candidate_catalysts_and_risks(self):
        captured = []

        def _invoke(input, config=None, **kwargs):
            captured.append(input)
            return AIMessage(content="MACRO REGIME: neutral")

        llm = RunnableLambda(_invoke)
        agent = create_macro_summary_agent(llm)
        state = {
            "scan_summary": {
                "executive_summary": "Rotation into energy and AI",
                "stocks_to_investigate": [
                    {
                        "ticker": "OXY",
                        "conviction": "high",
                        "thesis_angle": "energy alpha",
                        "key_catalysts": ["OPEC+ decision", "buyback acceleration"],
                        "risks": ["demand destruction", "policy error"],
                    }
                ],
            },
            "messages": [],
            "analysis_date": "2026-03-26",
        }

        agent(state)

        prompt = captured[0].to_messages()[0].content
        assert "OXY | high | energy alpha" in prompt
        assert "catalysts: OPEC+ decision, buyback acceleration" in prompt
        assert "risks: demand destruction, policy error" in prompt


# ---------------------------------------------------------------------------
# MacroSummaryAgent — macro_memory integration
# ---------------------------------------------------------------------------


class TestMacroSummaryAgentMemory:
    """Verify macro_memory interaction without hitting MongoDB."""

    def test_no_memory_context_is_empty_string_on_no_data_path(self):
        """NO-DATA path raises RuntimeError."""
        agent = create_macro_summary_agent(MagicMock())
        with pytest.raises(RuntimeError):
            agent({"scan_summary": {}, "messages": [], "analysis_date": ""})

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

    def test_empty_llm_output_raises_runtime_error(self):
        """Empty LLM output raises instead of returning an empty micro brief."""
        llm_mock, _ = _make_chain_mock("")
        agent = create_micro_summary_agent(llm_mock)
        state = {
            "holding_reviews": "{}",
            "prioritized_candidates": "[]",
            "ticker_analyses": {},
            "messages": [],
            "analysis_date": "2026-03-26",
        }

        with pytest.raises(RuntimeError, match="micro_summary_agent.*empty"):
            agent(state)

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


class TestMicroSummaryAgentSnapshotCompaction:
    def test_analysis_snapshot_preserves_decision_tail(self):
        long_decision = (
            "Rating: Buy\nExecutive Summary: "
            + ("Alpha thesis. " * 120)
            + "Stop Loss: 205.00\nTake Profit: 260.00\n"
        )

        snapshot = _analysis_snapshot(
            {
                "analysis_status": "completed",
                "final_trade_decision": long_decision,
                "trader_investment_plan": "Entry near support. " * 40 + "Sizing: 1%.",
                "investment_plan": "Research note. " * 40 + "Catalyst date: 2026-04-15.",
                "market_report": "Trend context. " * 30 + "Support: $210.00.",
                "fundamentals_report": "Fundamental context. " * 30 + "FCF margin: 28.4%.",
            }
        )

        assert snapshot["rating"] == "Buy"
        assert "Rating: Buy" in snapshot["final_trade_decision"]
        assert "Stop Loss: 205.00" in snapshot["final_trade_decision"]
        assert "Take Profit: 260.00" in snapshot["final_trade_decision"]
        assert "Sizing: 1%." in snapshot["trader_plan"]
        assert "Catalyst date: 2026-04-15." in snapshot["research_plan"]
        assert "Support: $210.00." in snapshot["market_report"]
        assert "FCF margin: 28.4%." in snapshot["fundamentals_report"]

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


class TestSummaryAgentMemoryFiltering:
    """Verify summary agents pass analysis_date into memory context lookups."""

    def test_macro_summary_forwards_analysis_date_to_memory_as_of_date(self):
        mock_memory = MagicMock()
        mock_memory.build_macro_context.return_value = "past context"

        llm = _make_runnable_llm("MACRO REGIME: neutral\nKEY NUMBERS: VIX=18")
        agent = create_macro_summary_agent(llm, macro_memory=mock_memory)
        state = {
            "analysis_date": "2026-03-20",
            "scan_summary": {"executive_summary": "Markets are mixed"},
            "messages": [],
        }

        agent(state)

        mock_memory.build_macro_context.assert_called_once_with(limit=3, as_of_date="2026-03-20")

    @pytest.mark.parametrize(
        "state",
        [
            {"scan_summary": {"executive_summary": "Markets are mixed"}, "messages": []},
            {
                "analysis_date": "   ",
                "scan_summary": {"executive_summary": "Markets are mixed"},
                "messages": [],
            },
        ],
    )
    def test_macro_summary_memory_requires_analysis_date(self, state):
        mock_memory = MagicMock()

        llm = _make_runnable_llm("MACRO REGIME: neutral\nKEY NUMBERS: VIX=18")
        agent = create_macro_summary_agent(llm, macro_memory=mock_memory)

        with pytest.raises(RuntimeError, match="macro_summary_agent.*analysis_date.*as_of_date"):
            agent(state)

        mock_memory.build_macro_context.assert_not_called()

    def test_micro_summary_forwards_analysis_date_to_each_memory_lookup(self):
        mock_memory = MagicMock()
        mock_memory.build_context.return_value = "ticker context"

        llm = _make_runnable_llm(
            "HOLDINGS TABLE:\n| AAPL | HOLD | NO DATA | none | ticker context |"
        )
        agent = create_micro_summary_agent(llm, micro_memory=mock_memory)
        state = {
            "analysis_date": "2026-03-20",
            "holding_reviews": json.dumps(
                {"AAPL": {"recommendation": "HOLD", "confidence": "high"}}
            ),
            "prioritized_candidates": json.dumps(
                [
                    {
                        "ticker": "MSFT",
                        "conviction": "high",
                        "thesis_angle": "AI infrastructure",
                    }
                ]
            ),
            "ticker_analyses": {},
            "messages": [],
        }

        agent(state)

        mock_memory.build_context.assert_has_calls(
            [
                call("AAPL", limit=2, as_of_date="2026-03-20"),
                call("MSFT", limit=2, as_of_date="2026-03-20"),
            ]
        )
        assert mock_memory.build_context.call_count == 2

    @pytest.mark.parametrize(
        "state",
        [
            {
                "holding_reviews": json.dumps(
                    {"AAPL": {"recommendation": "HOLD", "confidence": "high"}}
                ),
                "prioritized_candidates": "[]",
                "ticker_analyses": {},
                "messages": [],
            },
            {
                "analysis_date": "   ",
                "holding_reviews": json.dumps(
                    {"AAPL": {"recommendation": "HOLD", "confidence": "high"}}
                ),
                "prioritized_candidates": "[]",
                "ticker_analyses": {},
                "messages": [],
            },
        ],
    )
    def test_micro_summary_memory_requires_analysis_date(self, state):
        mock_memory = MagicMock()

        llm = _make_runnable_llm(
            "HOLDINGS TABLE:\n| AAPL | HOLD | NO DATA | none | ticker context |"
        )
        agent = create_micro_summary_agent(llm, micro_memory=mock_memory)

        with pytest.raises(RuntimeError, match="micro_summary_agent.*analysis_date.*as_of_date"):
            agent(state)

        mock_memory.build_context.assert_not_called()


class _StructuredLLMCapture:
    """Minimal structured-output LLM stub that captures the PM prompt text."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.captured_prompt = ""

    def with_structured_output(self, schema):
        def _invoke(prompt_value):
            self.captured_prompt = prompt_value.to_string()
            return schema(**self.payload)

        return RunnableLambda(_invoke)


class TestPMDecisionAgentInputs:
    def test_pm_prompt_includes_direct_candidate_deep_dive_summaries(self):
        """PM agent receives direct deep-dive summaries from prioritized candidates."""
        llm = _StructuredLLMCapture(_valid_pm_payload())
        agent = create_pm_decision_agent(llm)
        state = {
            "macro_brief": "MACRO REGIME: risk-off",
            "micro_brief": "Micro brief placeholder",
            "prioritized_candidates": (
                '[{"ticker":"AAPL","conviction":"high","thesis_angle":"growth",'
                '"priority_score":0.92,"candidate_final_trade_decision_summary":"Rating: Buy\\nExecutive Summary: durable moat"}]'
            ),
            "portfolio_data": '{"portfolio":{"cash":1000,"total_value":10000},"holdings":[]}',
            "messages": [],
            "analysis_date": "2026-03-30",
        }

        result = agent(state)

        assert isinstance(result["pm_decision"], str)
        assert "Input B — Direct Candidate Final Trade Decision Summaries" in llm.captured_prompt
        assert "durable moat" in llm.captured_prompt
        assert "AAPL" in llm.captured_prompt

    def test_pm_prompt_ignores_prior_message_history(self):
        """PM agent should rebuild its prompt from state data, not replay prior chat history."""
        llm = _StructuredLLMCapture(_valid_pm_payload())
        agent = create_pm_decision_agent(llm)
        state = {
            "macro_brief": "macro",
            "micro_brief": "micro",
            "prioritized_candidates": "[]",
            "portfolio_data": "{}",
            "messages": [AIMessage(content="prior message that should not be replayed")],
            "analysis_date": "2026-03-31",
        }

        result = agent(state)

        assert isinstance(result["pm_decision"], str)
        assert "prior message that should not be replayed" not in llm.captured_prompt
        assert "macro" in llm.captured_prompt
        assert "micro" in llm.captured_prompt

    def test_pm_retry_records_each_failure_with_breaker(self, monkeypatch):
        from tradingagents.agents.portfolio import pm_decision_agent as pm_module

        class _RecordingBreaker:
            def __init__(self):
                self.failures: list[str] = []
                self.successes: list[str] = []

            def assert_available(self, node_name: str) -> None:
                return None

            def record_failure(self, node_name: str, reason: str) -> None:
                self.failures.append(reason)

            def record_success(self, node_name: str) -> None:
                self.successes.append(node_name)

        class _FailingStructuredLLM:
            def with_structured_output(self, schema):
                def _invoke(_prompt_value):
                    raise ValueError("synthetic structured-output failure")

                return RunnableLambda(_invoke)

        breaker = _RecordingBreaker()
        monkeypatch.setattr(pm_module, "circuit_breaker_from_config", lambda cfg: breaker)
        monkeypatch.setattr(pm_module.time, "sleep", lambda _: None)

        agent = create_pm_decision_agent(_FailingStructuredLLM())
        state = {
            "macro_brief": "macro",
            "micro_brief": "micro",
            "prioritized_candidates": "[]",
            "portfolio_data": "{}",
            "messages": [],
            "analysis_date": "2026-03-31",
        }

        with pytest.raises(RuntimeError, match="structured output failed after 3 attempts"):
            agent(state)

        assert len(breaker.failures) == 3
        assert all("synthetic structured-output failure" in reason for reason in breaker.failures)
        assert breaker.successes == []

    def test_pm_retry_prompt_includes_executable_buy_guidance(self, monkeypatch):
        from tradingagents.agents.portfolio import pm_decision_agent as pm_module

        class _RecordingBreaker:
            def assert_available(self, node_name: str) -> None:
                return None

            def record_failure(self, node_name: str, reason: str) -> None:
                return None

            def record_success(self, node_name: str) -> None:
                return None

        class _RetryCaptureLLM:
            def __init__(self):
                self.calls = 0
                self.retry_message = ""

            def with_structured_output(self, schema):
                def _invoke(prompt_value):
                    self.calls += 1
                    if self.calls == 1:
                        return schema(
                            macro_regime="risk-off",
                            regime_alignment_note="needs executable guidance",
                            sells=[],
                            buys=[
                                {
                                    "ticker": "AAPL",
                                    "shares": 2.0,
                                    "price_target": 240.0,
                                    "stop_loss": 205.0,
                                    "take_profit": 260.0,
                                    "sector": "Technology",
                                    "rationale": "missing executable fields",
                                    "thesis": "test",
                                    "macro_alignment": "test",
                                    "memory_note": "test",
                                    "position_sizing_logic": "test",
                                }
                            ],
                            holds=[],
                            cash_reserve_pct=0.1,
                            portfolio_thesis="test",
                            risk_summary="test",
                            forensic_report={
                                "regime_alignment": "test",
                                "key_risks": ["test"],
                                "decision_confidence": "medium",
                                "position_sizing_rationale": "test",
                            },
                        )

                    self.retry_message = "\n".join(
                        message.content
                        for message in prompt_value.to_messages()
                        if getattr(message, "type", "") == "human"
                    )
                    return schema(**_valid_pm_payload())

                return RunnableLambda(_invoke)

        monkeypatch.setattr(
            pm_module, "circuit_breaker_from_config", lambda cfg: _RecordingBreaker()
        )
        monkeypatch.setattr(pm_module.time, "sleep", lambda _: None)

        llm = _RetryCaptureLLM()
        agent = create_pm_decision_agent(llm)
        state = {
            "macro_brief": "macro",
            "micro_brief": "micro",
            "prioritized_candidates": "[]",
            "portfolio_data": "{}",
            "messages": [],
            "analysis_date": "2026-03-31",
        }

        result = agent(state)

        assert isinstance(result["pm_decision"], str)
        assert llm.calls == 2
        assert "entry_price" in llm.retry_message
        assert "limit_price" in llm.retry_message
        assert "max_chase_price" in llm.retry_message
        assert "valid_as_of" in llm.retry_message
        assert "Every BUY must be executable as a limit order" in llm.retry_message
        assert "entry_price <= max_chase_price <= limit_price" in llm.retry_message


class TestSummaryAgentsRobustness:
    def test_macro_summary_agent_ignores_prior_message_history(self):
        captured = []

        def _invoke(input, config=None, **kwargs):
            captured.append(input)
            return AIMessage(content="MACRO REGIME: neutral")

        llm = RunnableLambda(_invoke)
        agent = create_macro_summary_agent(llm)
        state = {
            "messages": [AIMessage(content="This prior message should be ignored.")],
            "scan_summary": {"executive_summary": "Flat markets"},
            "analysis_date": "2026-03-31",
        }

        agent(state)

        # The chain passes a ChatPromptValue to the LLM
        messages = captured[0].to_messages()
        assert len(messages) == 1
        assert messages[0].type == "system"
        assert "This prior message should be ignored." not in messages[0].content

    def test_micro_summary_agent_ignores_prior_message_history(self):
        captured = []

        def _invoke(input, config=None, **kwargs):
            captured.append(input)
            return AIMessage(content="Micro brief")

        llm = RunnableLambda(_invoke)
        agent = create_micro_summary_agent(llm)
        state = {
            "messages": [AIMessage(content="This prior message should be ignored.")],
            "holding_reviews": "{}",
            "prioritized_candidates": "[]",
            "analysis_date": "2026-03-31",
        }

        agent(state)

        messages = captured[0].to_messages()
        assert len(messages) == 1
        assert messages[0].type == "system"
        assert "This prior message should be ignored." not in messages[0].content

    def test_holding_reviewer_ignores_prior_message_history(self):
        captured = []

        def _invoke(input, config=None, **kwargs):
            captured.append(input)
            return AIMessage(content="{}")

        class MockLLM:
            def __init__(self):
                self.runnable = RunnableLambda(_invoke)

            def bind_tools(self, tools):
                return self.runnable

        llm = MockLLM()
        agent = create_holding_reviewer(llm)
        state = {
            "messages": [AIMessage(content="This prior message should be ignored.")],
            "portfolio_data": json.dumps({"holdings": [{"ticker": "AAPL"}]}),
            "analysis_date": "2026-03-31",
        }

        agent(state)

        messages = captured[0].to_messages()
        assert len(messages) == 1
        assert messages[0].type == "system"
        assert "This prior message should be ignored." not in messages[0].content
