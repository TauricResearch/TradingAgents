"""Tests for the SignalFusion scaffolding landed in commit 1.

These cover the pure-Python aggregation primitives, the dict-merge
reducer, the strict-extraction helper (with all three fallback rungs),
and the AnalystSignal schema's sign-consistency normalisation. Graph
topology selection (parallel vs legacy serial) is exercised in a
smaller integration test that compiles both graphs and inspects the
node sets — no LLM calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from tradingagents.agents.schemas import (
    AnalystSignal,
    SignalDirection,
    render_analyst_signal_summary,
)
from tradingagents.agents.utils.agent_states import _merge_analyst_signals
from tradingagents.agents.utils.structured import (
    _normalise_sign_consistency,
    extract_analyst_signal,
    extract_structured_with_repair,
)
from tradingagents.graph.signal_fusion import (
    compute_composite_score,
    create_signal_fusion_node,
    detect_disagreement,
    equal_weights,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(
    *,
    direction: SignalDirection = SignalDirection.BULLISH,
    score: float = 0.5,
    confidence: float = 0.8,
    evidence_count: int = 3,
    key_evidence: list[str] | None = None,
    report: str = "## Sample report\n\nBody.",
) -> AnalystSignal:
    return AnalystSignal(
        report=report,
        direction=direction,
        score=score,
        confidence=confidence,
        evidence_count=evidence_count,
        key_evidence=key_evidence or ["evidence A", "evidence B"],
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalystSignalSchema:
    def test_score_bounds_enforced(self):
        with pytest.raises(ValidationError):
            AnalystSignal(
                report="x",
                direction=SignalDirection.BULLISH,
                score=1.5,
                confidence=0.5,
                evidence_count=0,
            )

    def test_confidence_bounds_enforced(self):
        with pytest.raises(ValidationError):
            AnalystSignal(
                report="x",
                direction=SignalDirection.NEUTRAL,
                score=0.0,
                confidence=1.1,
                evidence_count=0,
            )

    def test_key_evidence_capped_at_five(self):
        with pytest.raises(ValidationError):
            AnalystSignal(
                report="x",
                direction=SignalDirection.BULLISH,
                score=0.5,
                confidence=0.7,
                evidence_count=6,
                key_evidence=["a", "b", "c", "d", "e", "f"],
            )

    def test_render_summary_includes_direction_and_evidence(self):
        sig = _make_signal(
            direction=SignalDirection.BEARISH,
            score=-0.6,
            confidence=0.75,
            key_evidence=["debt rising", "guidance cut"],
        )
        md = render_analyst_signal_summary(sig)
        assert "Bearish" in md
        assert "-0.60" in md
        assert "- debt rising" in md
        assert "- guidance cut" in md


# ---------------------------------------------------------------------------
# Aggregation primitives
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEqualWeights:
    def test_uniform_distribution(self):
        w = equal_weights(["market", "social", "news", "fundamentals"])
        assert w == {
            "market": 0.25,
            "social": 0.25,
            "news": 0.25,
            "fundamentals": 0.25,
        }

    def test_empty_input_returns_empty(self):
        assert equal_weights([]) == {}

    def test_single_channel_gets_full_weight(self):
        assert equal_weights(["market"]) == {"market": 1.0}


@pytest.mark.unit
class TestCompositeScore:
    def test_equal_weights_average_with_confidence(self):
        signals = {
            "market": _make_signal(score=0.6, confidence=1.0),
            "social": _make_signal(score=-0.4, confidence=1.0),
        }
        w = equal_weights(list(signals.keys()))
        # 0.5 * 0.6 * 1.0 + 0.5 * -0.4 * 1.0 = 0.1
        assert compute_composite_score(signals, w) == pytest.approx(0.1)

    def test_low_confidence_dampens_contribution(self):
        signals = {
            "market": _make_signal(score=1.0, confidence=0.0),
            "social": _make_signal(score=1.0, confidence=1.0),
        }
        w = equal_weights(list(signals.keys()))
        assert compute_composite_score(signals, w) == pytest.approx(0.5)

    def test_missing_channel_in_weights_is_ignored(self):
        signals = {"market": _make_signal(score=0.8, confidence=1.0)}
        # weights lacks "market" entirely
        assert compute_composite_score(signals, {"social": 1.0}) == 0.0

    def test_no_signals_returns_zero(self):
        assert compute_composite_score({}, {}) == 0.0


@pytest.mark.unit
class TestDetectDisagreement:
    def test_returns_widest_pair(self):
        signals = {
            "market": _make_signal(score=0.71),
            "social": _make_signal(score=-0.42, direction=SignalDirection.BEARISH),
            "news": _make_signal(score=0.10),
        }
        result = detect_disagreement(signals)
        assert len(result) == 1
        # market (+0.71) vs social (-0.42) — the largest signed gap
        assert "market" in result[0]
        assert "sentiment" in result[0]  # display name for "social"
        assert "+0.71" in result[0]
        assert "-0.42" in result[0]

    def test_returns_empty_when_zero_or_one_signal(self):
        assert detect_disagreement({}) == []
        assert detect_disagreement({"market": _make_signal()}) == []

    def test_returns_empty_when_all_scores_equal(self):
        signals = {
            "market": _make_signal(score=0.3),
            "social": _make_signal(score=0.3),
        }
        assert detect_disagreement(signals) == []


@pytest.mark.unit
class TestMergeAnalystSignalsReducer:
    def test_disjoint_keys_combine(self):
        a = {"market": _make_signal(score=0.5)}
        b = {"social": _make_signal(score=-0.2, direction=SignalDirection.BEARISH)}
        merged = _merge_analyst_signals(a, b)
        assert set(merged.keys()) == {"market", "social"}

    def test_right_wins_on_key_collision(self):
        new = _make_signal(score=-0.9, direction=SignalDirection.BEARISH)
        merged = _merge_analyst_signals({"market": _make_signal(score=0.5)}, {"market": new})
        assert merged["market"] is new

    def test_handles_none_inputs(self):
        only_b = _merge_analyst_signals(None, {"market": _make_signal()})
        assert set(only_b.keys()) == {"market"}
        only_a = _merge_analyst_signals({"market": _make_signal()}, None)
        assert set(only_a.keys()) == {"market"}
        assert _merge_analyst_signals(None, None) == {}


# ---------------------------------------------------------------------------
# Fusion node end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSignalFusionNode:
    def test_equal_weights_produces_expected_state_delta(self):
        node = create_signal_fusion_node()  # default = equal weights
        state = {
            "analyst_signals": {
                "market": _make_signal(score=0.5, confidence=1.0),
                "social": _make_signal(score=-0.5, confidence=1.0, direction=SignalDirection.BEARISH),
            },
        }
        update = node(state)
        assert update["signal_weights"] == {"market": 0.5, "social": 0.5}
        assert update["composite_score"] == pytest.approx(0.0)
        assert len(update["disagreement_axes"]) == 1

    def test_no_signals_returns_zero_composite_no_crash(self):
        node = create_signal_fusion_node()
        update = node({"analyst_signals": {}})
        assert update["signal_weights"] == {}
        assert update["composite_score"] == 0.0
        assert update["disagreement_axes"] == []

    def test_custom_weight_fn_is_respected(self):
        node = create_signal_fusion_node(weight_fn=lambda chans: {c: 1.0 for c in chans})
        state = {"analyst_signals": {"market": _make_signal(score=0.4, confidence=1.0)}}
        update = node(state)
        assert update["signal_weights"] == {"market": 1.0}
        assert update["composite_score"] == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# Extraction helper — structured, repair, heuristic
# ---------------------------------------------------------------------------


def _structured_llm_that_returns(signal: AnalystSignal):
    structured = MagicMock()
    structured.invoke.return_value = signal
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestExtractAnalystSignalHappyPath:
    def test_structured_output_returned_directly(self):
        target = _make_signal(
            direction=SignalDirection.BULLISH,
            score=0.65,
            confidence=0.8,
            evidence_count=4,
            key_evidence=["earnings beat", "margins up"],
            report="full markdown body here, more than 50% of the input length to avoid restore",
        )
        llm = _structured_llm_that_returns(target)
        result = extract_analyst_signal(
            llm=llm,
            markdown_report=target.report,
            analyst_name="Market Analyst",
            ticker="NVDA",
        )
        assert result.direction == SignalDirection.BULLISH
        assert result.score == pytest.approx(0.65)
        assert result.evidence_count == 4

    def test_short_returned_report_is_restored_from_input(self):
        # Some providers truncate the echoed markdown.
        returned = _make_signal(report="x")
        full_markdown = "A" * 4000
        llm = _structured_llm_that_returns(returned)
        result = extract_analyst_signal(
            llm=llm,
            markdown_report=full_markdown,
            analyst_name="News Analyst",
            ticker="TSLA",
        )
        assert result.report == full_markdown


@pytest.mark.unit
class TestExtractAnalystSignalSelfRepair:
    def test_repair_path_succeeds_with_json_string(self):
        # First call raises; the plain LLM (used for the JSON repair pass)
        # returns a valid JSON object as a string.
        structured = MagicMock()
        structured.invoke.side_effect = RuntimeError("provider hiccup")
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        repair_payload = {
            "report": "synthetic",
            "direction": "bearish",
            "score": -0.4,
            "confidence": 0.6,
            "evidence_count": 2,
            "key_evidence": ["margin compression"],
        }
        llm.invoke.return_value = MagicMock(content=json.dumps(repair_payload))

        result = extract_analyst_signal(
            llm=llm,
            markdown_report="X" * 400,  # >> 50% threshold
            analyst_name="Fundamentals Analyst",
            ticker="JNJ",
        )
        assert result.direction == SignalDirection.BEARISH
        assert result.score == pytest.approx(-0.4)
        # restored report (synthetic was shorter than 50% of input)
        assert result.report.startswith("X")


@pytest.mark.unit
class TestExtractAnalystSignalHeuristicFallback:
    def test_falls_back_to_final_proposal_keyword(self):
        # Both structured and repair fail; heuristic parses the markdown.
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("no structured output")
        llm.invoke.return_value = MagicMock(content="garbage that doesn't parse as JSON")
        report = (
            "## Market analysis\n\n"
            "Indicators look constructive across the board.\n\n"
            "FINAL TRANSACTION PROPOSAL: **BUY**"
        )
        result = extract_analyst_signal(
            llm=llm,
            markdown_report=report,
            analyst_name="Market Analyst",
            ticker="NVDA",
        )
        assert result.direction == SignalDirection.BULLISH
        assert result.confidence == 0.3
        assert result.report == report

    def test_neutral_fallback_when_no_signal_in_report(self):
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError
        llm.invoke.return_value = MagicMock(content="still not JSON")
        report = "Report body without explicit direction keywords."
        result = extract_analyst_signal(
            llm=llm,
            markdown_report=report,
            analyst_name="News Analyst",
            ticker="TSLA",
        )
        assert result.direction == SignalDirection.NEUTRAL
        assert result.score == 0.0


@pytest.mark.unit
class TestSignConsistencyNormalisation:
    def test_bullish_with_negative_score_clamps_positive(self):
        sig = AnalystSignal(
            report="x",
            direction=SignalDirection.BULLISH,
            score=-0.3,
            confidence=0.5,
            evidence_count=0,
        )
        out = _normalise_sign_consistency(sig, "test")
        assert out.score == 0.1

    def test_bearish_with_positive_score_clamps_negative(self):
        sig = AnalystSignal(
            report="x",
            direction=SignalDirection.BEARISH,
            score=0.2,
            confidence=0.5,
            evidence_count=0,
        )
        out = _normalise_sign_consistency(sig, "test")
        assert out.score == -0.1

    def test_neutral_with_large_score_clamps_zero(self):
        sig = AnalystSignal(
            report="x",
            direction=SignalDirection.NEUTRAL,
            score=0.8,
            confidence=0.5,
            evidence_count=0,
        )
        out = _normalise_sign_consistency(sig, "test")
        assert out.score == 0.0

    def test_consistent_signal_passes_unchanged(self):
        sig = AnalystSignal(
            report="x",
            direction=SignalDirection.BULLISH,
            score=0.7,
            confidence=0.5,
            evidence_count=0,
        )
        out = _normalise_sign_consistency(sig, "test")
        assert out is sig


# ---------------------------------------------------------------------------
# Graph topology selection
# ---------------------------------------------------------------------------


def _make_graph_setup(*, signal_fusion_enabled: bool):
    """Build a GraphSetup instance with stub LLMs and tool nodes.

    Compiling the graph exercises node IDs, edges, and conditional
    edges — enough to verify the topology branch without an LLM call.
    """
    from langgraph.prebuilt import ToolNode
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.graph.setup import GraphSetup

    # ToolNode requires at least one BaseTool-compatible callable; use a
    # @tool-decorated stub so initialisation does not blow up.
    from langchain_core.tools import tool as tool_decorator

    @tool_decorator
    def _noop_tool(x: str) -> str:
        """No-op tool used only to satisfy ToolNode initialisation."""
        return x

    stub_llm = MagicMock()
    stub_llm.bind_tools.return_value = stub_llm
    stub_llm.with_structured_output.return_value = stub_llm

    tool_nodes = {
        "market": ToolNode([_noop_tool], messages_key="market_messages" if signal_fusion_enabled else "messages"),
        "social": ToolNode([_noop_tool], messages_key="sentiment_messages" if signal_fusion_enabled else "messages"),
        "news": ToolNode([_noop_tool], messages_key="news_messages" if signal_fusion_enabled else "messages"),
        "fundamentals": ToolNode([_noop_tool], messages_key="fundamentals_messages" if signal_fusion_enabled else "messages"),
    }

    cl = ConditionalLogic(
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        parallel_analysts=signal_fusion_enabled,
    )
    return GraphSetup(
        stub_llm,
        stub_llm,
        tool_nodes,
        cl,
        signal_fusion_enabled=signal_fusion_enabled,
    )


@pytest.mark.unit
class TestGraphTopologySelection:
    def test_parallel_graph_has_fusion_and_extract_nodes(self):
        gs = _make_graph_setup(signal_fusion_enabled=True)
        workflow = gs.setup_graph(["market", "social", "news", "fundamentals"])
        compiled = workflow.compile()
        node_names = set(compiled.get_graph().nodes.keys())

        assert "Signal Fusion" in node_names
        assert "Extract Market" in node_names
        assert "Extract Social" in node_names
        assert "Extract News" in node_names
        assert "Extract Fundamentals" in node_names
        # Legacy nodes must be absent in the parallel graph.
        assert "Msg Clear Market" not in node_names

    def test_legacy_graph_preserves_serial_topology(self):
        gs = _make_graph_setup(signal_fusion_enabled=False)
        workflow = gs.setup_graph(["market", "social", "news", "fundamentals"])
        compiled = workflow.compile()
        node_names = set(compiled.get_graph().nodes.keys())

        # Legacy nodes present, fusion nodes absent.
        assert "Msg Clear Market" in node_names
        assert "Msg Clear Fundamentals" in node_names
        assert "Signal Fusion" not in node_names
        assert "Extract Market" not in node_names

    def test_unknown_analyst_raises(self):
        gs = _make_graph_setup(signal_fusion_enabled=True)
        with pytest.raises(ValueError, match="unknown analyst"):
            gs.setup_graph(["market", "not_a_real_analyst"])

    def test_empty_analyst_list_raises(self):
        gs = _make_graph_setup(signal_fusion_enabled=True)
        with pytest.raises(ValueError, match="no analysts selected"):
            gs.setup_graph([])


# ---------------------------------------------------------------------------
# Conditional logic routing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConditionalLogicAnalystRoute:
    def test_parallel_routes_to_extract_when_no_tool_calls(self):
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic(parallel_analysts=True)
        last = MagicMock()
        last.tool_calls = []
        assert cl.should_continue_market({"market_messages": [last]}) == "Extract Market"

    def test_serial_routes_to_msg_clear_when_no_tool_calls(self):
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic(parallel_analysts=False)
        last = MagicMock()
        last.tool_calls = []
        assert cl.should_continue_market({"messages": [last]}) == "Msg Clear Market"

    def test_tool_call_present_routes_to_tools(self):
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic(parallel_analysts=True)
        last = MagicMock()
        last.tool_calls = [{"name": "get_stock_data"}]
        assert cl.should_continue_market({"market_messages": [last]}) == "tools_market"

    def test_budget_cap_forces_exit_even_with_pending_tool_calls(self):
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic(parallel_analysts=True, max_analyst_tool_calls=2)
        prior_calls = [MagicMock(tool_calls=[{"name": "t"}]) for _ in range(2)]
        last = MagicMock(tool_calls=[{"name": "t"}])
        # 2 prior tool calls + 1 pending — budget already reached, so the
        # router should exit via Extract rather than dispatch another batch.
        state = {"market_messages": prior_calls + [last]}
        assert cl.should_continue_market(state) == "Extract Market"
