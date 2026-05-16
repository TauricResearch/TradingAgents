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
    # Use ``is None`` rather than truthiness so callers can pass an
    # explicit empty list to suppress the default evidence list.
    if key_evidence is None:
        key_evidence = ["evidence A", "evidence B"]
    return AnalystSignal(
        report=report,
        direction=direction,
        score=score,
        confidence=confidence,
        evidence_count=evidence_count,
        key_evidence=key_evidence,
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


# ---------------------------------------------------------------------------
# Commit 2: weight estimator
# ---------------------------------------------------------------------------


def _synthetic_history(start: str, end: str, *, seed: int = 7) -> "pd.DataFrame":
    """Build a deterministic OHLCV DataFrame for tests."""
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, end=end, freq="B")
    if len(idx) < 2:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    # Geometric random walk for Close; volume around 1e6 with bursts.
    returns = rng.normal(0.0005, 0.012, size=len(idx))
    close = 100.0 * np.cumprod(1 + returns)
    volume = (1.0 + rng.normal(0, 0.2, size=len(idx)).clip(-0.5, 1.5)) * 1_000_000
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.005,
            "Low": close * 0.995,
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )


@pytest.mark.unit
class TestRollingCorrelationEstimator:
    def _build(self, *, history_fn=None, cache_dir=None, **cfg_kwargs):
        from tradingagents.dataflows.signal_weights import (
            RollingCorrelationConfig,
            RollingCorrelationEstimator,
        )
        return RollingCorrelationEstimator(
            fetch_history=history_fn or (lambda t, s, e: _synthetic_history(s, e, seed=hash(t) & 0xFFFF)),
            benchmark_ticker="SPY",
            cache_dir=cache_dir,
            config=RollingCorrelationConfig(**cfg_kwargs),
        )

    def test_lookahead_guard_rejects_history_containing_trade_date(self, tmp_path):
        """The estimator must refuse to fit if any feature row is dated >= as_of."""
        import pandas as pd

        def _peeky_history(ticker, start, end):
            df = _synthetic_history(start, end)
            # Inject a row on the trade date itself — this is the
            # lookahead bug we want to catch.
            cutoff = pd.Timestamp(end)
            df.loc[cutoff] = df.iloc[-1]
            return df

        est = self._build(history_fn=_peeky_history, cache_dir=tmp_path)
        # The estimator catches the lookahead internally and falls back
        # to equal weights; the equal-weights fallback is the safe
        # behavior under insufficient/contaminated data.
        weights = est.get_weights(
            ticker="NVDA",
            as_of_date="2025-06-01",
            available_channels=["market", "social", "news", "fundamentals"],
        )
        # Exact equality under the floor + softmax-of-uniform = uniform.
        for v in weights.values():
            assert v == pytest.approx(0.25, abs=0.01)

    def test_min_weight_floor_enforced(self, tmp_path):
        est = self._build(cache_dir=tmp_path, min_weight=0.10)
        weights = est.get_weights(
            ticker="ABCD",
            as_of_date="2025-06-01",
            available_channels=["market", "social", "news", "fundamentals"],
        )
        for v in weights.values():
            assert v >= 0.10 - 1e-6
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    def test_weights_sum_to_one(self, tmp_path):
        est = self._build(cache_dir=tmp_path)
        weights = est.get_weights(
            ticker="XYZ",
            as_of_date="2025-06-01",
            available_channels=["market", "social", "news", "fundamentals"],
        )
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    def test_cache_hit_on_second_call(self, tmp_path):
        """A second call with the same args reads from CSV cache, not from history."""
        from tradingagents.dataflows.signal_weights import RollingCorrelationEstimator

        calls = {"count": 0}

        def _counting_history(t, s, e):
            calls["count"] += 1
            return _synthetic_history(s, e)

        est = self._build(history_fn=_counting_history, cache_dir=tmp_path)
        w1 = est.get_weights(
            ticker="NVDA",
            as_of_date="2025-06-01",
            available_channels=["market", "social", "news", "fundamentals"],
        )
        first_call_count = calls["count"]
        w2 = est.get_weights(
            ticker="NVDA",
            as_of_date="2025-06-01",
            available_channels=["market", "social", "news", "fundamentals"],
        )
        # Cache hit means history was NOT re-fetched.
        assert calls["count"] == first_call_count
        assert w1 == w2

    def test_subset_of_channels_renormalises(self, tmp_path):
        """Requesting a subset returns weights that sum to 1 over that subset."""
        est = self._build(cache_dir=tmp_path)
        weights = est.get_weights(
            ticker="ABCD",
            as_of_date="2025-06-01",
            available_channels=["market", "news"],
        )
        assert set(weights.keys()) == {"market", "news"}
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    def test_no_channels_returns_empty(self, tmp_path):
        est = self._build(cache_dir=tmp_path)
        assert est.get_weights(
            ticker="NVDA",
            as_of_date="2025-06-01",
            available_channels=[],
        ) == {}


@pytest.mark.unit
class TestBuildWeightEstimator:
    def test_equal_method_returns_equal_estimator(self):
        from tradingagents.dataflows.signal_weights import (
            EqualWeightEstimator,
            build_weight_estimator,
        )
        est = build_weight_estimator(method="equal")
        assert isinstance(est, EqualWeightEstimator)

    def test_rolling_correlation_requires_fetch_history(self):
        from tradingagents.dataflows.signal_weights import build_weight_estimator
        with pytest.raises(ValueError, match="fetch_history"):
            build_weight_estimator(method="rolling_correlation")

    def test_rolling_lasso_aliases_to_rolling_correlation(self, tmp_path):
        from tradingagents.dataflows.signal_weights import (
            RollingCorrelationEstimator,
            build_weight_estimator,
        )
        est = build_weight_estimator(
            method="rolling_lasso",
            fetch_history=lambda t, s, e: _synthetic_history(s, e),
            cache_dir=tmp_path,
        )
        assert isinstance(est, RollingCorrelationEstimator)

    def test_unknown_method_raises(self):
        from tradingagents.dataflows.signal_weights import build_weight_estimator
        with pytest.raises(ValueError, match="Unknown"):
            build_weight_estimator(method="not_a_real_method")


# ---------------------------------------------------------------------------
# Commit 2: fusion prompt rendering
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFusionPromptRender:
    def test_preamble_present_when_weights_supplied(self):
        from tradingagents.agents.utils.fusion_prompt import render_fusion_prompt_parts

        parts = render_fusion_prompt_parts(
            market_report="full market report",
            sentiment_report="full sentiment report",
            news_report="full news report",
            fundamentals_report="full fundamentals report",
            analyst_signals={
                "market": _make_signal(score=0.5),
                "social": _make_signal(score=-0.4, direction=SignalDirection.BEARISH),
            },
            signal_weights={"market": 0.25, "social": 0.25, "news": 0.25, "fundamentals": 0.25},
            composite_score=0.42,
            disagreement_axes=["market (+0.71) vs sentiment (-0.42)"],
        )
        assert "Fused signal" in parts.fusion_preamble
        assert "+0.42" in parts.fusion_preamble
        assert "moderately bullish" in parts.fusion_preamble
        assert "Market" in parts.fusion_preamble
        assert "Key analyst disagreement" in parts.fusion_preamble
        # Above the compression threshold (default 0.10), all reports
        # are full markdown — no digestion happened.
        assert "full market report" in parts.market_block
        assert "full sentiment report" in parts.sentiment_block

    def test_no_preamble_when_weights_empty(self):
        from tradingagents.agents.utils.fusion_prompt import render_fusion_prompt_parts

        parts = render_fusion_prompt_parts(
            market_report="m",
            sentiment_report="s",
            news_report="n",
            fundamentals_report="f",
            analyst_signals={},
            signal_weights={},
            composite_score=0.0,
            disagreement_axes=[],
        )
        # Fusion-off path: preamble is empty, reports passed through verbatim.
        assert parts.fusion_preamble == ""
        assert parts.market_block == "m"
        assert parts.sentiment_block == "s"

    def test_compression_triggers_below_threshold(self):
        from tradingagents.agents.utils.fusion_prompt import (
            FusionPromptConfig,
            render_fusion_prompt_parts,
        )

        sig = _make_signal(
            direction=SignalDirection.BEARISH,
            score=-0.6,
            key_evidence=["debt rising", "margin compression"],
        )
        parts = render_fusion_prompt_parts(
            market_report="full market report here, many tokens",
            sentiment_report="full sentiment report here, many tokens",
            news_report="full news report here, many tokens",
            fundamentals_report="full fundamentals report here, many tokens",
            analyst_signals={"market": sig},
            signal_weights={"market": 0.05, "social": 0.45, "news": 0.30, "fundamentals": 0.20},
            composite_score=0.2,
            disagreement_axes=[],
            config=FusionPromptConfig(compress_threshold=0.10),
        )
        # market weight (0.05) < threshold (0.10) → compressed digest, not full
        assert "full market report" not in parts.market_block
        assert "debt rising" in parts.market_block
        assert "Bearish" in parts.market_block
        # Above-threshold reports stay full.
        assert "full sentiment report" in parts.sentiment_block

    def test_compression_falls_back_to_sentence_clip_when_no_key_evidence(self):
        from tradingagents.agents.utils.fusion_prompt import (
            FusionPromptConfig,
            render_fusion_prompt_parts,
        )

        sig = _make_signal(key_evidence=[])  # heuristic-fallback shape
        parts = render_fusion_prompt_parts(
            market_report="First sentence. Second sentence. Third sentence. Fourth sentence.",
            sentiment_report="",
            news_report="",
            fundamentals_report="",
            analyst_signals={"market": sig},
            signal_weights={"market": 0.05, "social": 0.95},
            composite_score=0.0,
            disagreement_axes=[],
            config=FusionPromptConfig(compress_threshold=0.10, compress_to_sentences=2),
        )
        # Clipped to first 2 sentences, plus the "downweighted" header.
        assert "Downweighted" in parts.market_block
        assert "First sentence" in parts.market_block
        assert "Second sentence" in parts.market_block
        assert "Fourth sentence" not in parts.market_block


# ---------------------------------------------------------------------------
# Commit 2: SignalFusion node with estimator
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSignalFusionNodeWithEstimator:
    def test_estimator_called_with_state_ticker_and_date(self):
        from tradingagents.graph.signal_fusion import create_signal_fusion_node

        calls = {}

        class _CaptureEstimator:
            def get_weights(self, *, ticker, as_of_date, available_channels):
                calls["ticker"] = ticker
                calls["as_of_date"] = as_of_date
                calls["channels"] = list(available_channels)
                return {c: 1.0 / len(available_channels) for c in available_channels}

        node = create_signal_fusion_node(weight_estimator=_CaptureEstimator())
        state = {
            "company_of_interest": "NVDA",
            "trade_date": "2025-06-01",
            "analyst_signals": {
                "market": _make_signal(score=0.5, confidence=1.0),
                "news": _make_signal(score=0.3, confidence=1.0),
            },
        }
        update = node(state)
        assert calls["ticker"] == "NVDA"
        assert calls["as_of_date"] == "2025-06-01"
        assert set(calls["channels"]) == {"market", "news"}
        assert update["composite_score"] == pytest.approx(0.4)

    def test_estimator_skipped_when_no_signals(self):
        from tradingagents.graph.signal_fusion import create_signal_fusion_node

        calls = {"count": 0}

        class _CaptureEstimator:
            def get_weights(self, **kw):
                calls["count"] += 1
                return {}

        node = create_signal_fusion_node(weight_estimator=_CaptureEstimator())
        update = node({"analyst_signals": {}, "company_of_interest": "x", "trade_date": "2025-01-01"})
        assert calls["count"] == 0
        assert update["composite_score"] == 0.0
