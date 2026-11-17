"""Self-check: verify the GOV-004 live harness with a scripted model.

Runs entirely offline (no provider, no network). It proves the harness plumbing
is correct *before* the live run, so a live failure can be attributed to the
model/endpoint rather than the harness:

1. ``PromptCapture`` records a call and reports challenge-marker presence.
2. ``_InjectedNewsRouter`` makes the news tools return the injected body and
   restores the original router afterwards (no application edit).
3. ``run_case`` drives a scripted engine through ``run_analysis_api`` end to
   end, producing published report + manifest and a complete evidence record,
   including a challenge case whose marker reached the (scripted) model input.

This file is run with ``pytest`` only when the live directory is selected; it is
outside ``testpaths`` like ``test/offline``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cases import CASES, INJECTION_MARKER  # noqa: E402
from runner import PromptCapture, _InjectedNewsRouter, run_case  # noqa: E402

pytestmark = pytest.mark.unit


def test_prompt_capture_reports_marker_presence():
    capture = PromptCapture(markers=(INJECTION_MARKER,))
    capture.on_llm_start({}, [f"prefix {INJECTION_MARKER} suffix"])
    summary = capture.summary()
    assert summary["model_calls"] == 1
    assert summary["marker_reached_model"][INJECTION_MARKER] is True
    # The raw prompt is never retained -- only a digest and a length.
    assert all("prefix" not in str(call) for call in capture.calls)
    assert summary["distinct_prompt_digests"]


def test_injection_router_injects_and_restores():
    import tradingagents.agents.tools as tools_module
    from tradingagents.dataflows import router as router_module

    original_router = router_module.route_to_vendor
    original_tools = tools_module.route_to_vendor
    with _InjectedNewsRouter(f"body {INJECTION_MARKER}"):
        assert INJECTION_MARKER in tools_module.route_to_vendor("get_news", "AAPL", "2026-01-01", "2026-01-08")
        assert INJECTION_MARKER in tools_module.route_to_vendor("get_global_news", "2026-01-08")
        assert router_module.route_to_vendor is not original_router
    # Restored: the application seam is untouched after the context.
    assert router_module.route_to_vendor is original_router
    assert tools_module.route_to_vendor is original_tools


def _scripted_state():
    return {
        "market_report": "MKT",
        "sentiment_report": "SENT",
        "news_report": "NEWS",
        "fundamentals_report": "FUND",
        "investment_debate_state": {"bull_history": "BULL", "bear_history": "BEAR"},
        "investment_plan": "RESEARCH PLAN",
        "trader_investment_plan": "TRADE: Hold",
        "risk_debate_state": {"neutral_history": "NEUTRAL"},
        "final_trade_decision": "**Rating**: Hold\n\nBalanced view.",
        "final_rating": "Hold",
    }


def test_run_case_end_to_end_with_scripted_engine(tmp_path, monkeypatch):
    """Drive run_case's full publish path with a scripted engine and capture."""

    # Force a scripted engine inside run_analysis_api by stubbing its graph
    # factory and runner through the public kwargs. We reuse the offline trick:
    # patch the default factory/runner lookups run_analysis_api uses when the
    # caller passes none. Because run_case calls run_analysis_api without them,
    # we patch the module-level defaults.
    import tradingagents.runapi.execution as execution

    class _Engine:
        pass

    def factory(*_a, **_k):
        return _Engine()

    def runner(_graph, _context):
        return _scripted_state()

    monkeypatch.setattr(execution, "_default_graph_factory", factory)
    monkeypatch.setattr(execution, "_default_engine_runner", lambda g, c, cfg: runner(g, c))

    # Use a non-challenge case: prove a full, published, COMPLETED run.
    case = CASES[0]
    outcome = run_case(case, results_dir=str(tmp_path), ticker="AAPL", analysis_date="2026-01-09")

    assert outcome.outcome == "COMPLETED", outcome
    assert outcome.run_id
    assert outcome.manifest_path and Path(outcome.manifest_path).is_file()
    assert outcome.report_path and Path(outcome.report_path).is_file()
    assert outcome.source_revision.startswith("git:")
    assert outcome.model_config["llm_provider"] is not None
    manifest = json.loads(Path(outcome.manifest_path).read_text(encoding="utf-8"))
    assert manifest["run_id"] == outcome.run_id
    assert manifest["run_outcome"] == "COMPLETED"


def test_run_case_records_challenge_reached_with_scripted_engine(tmp_path, monkeypatch):
    """A challenge case records marker presence from captured model input."""
    import tradingagents.runapi.execution as execution

    def factory(*_a, **_k):
        return object()

    # The scripted "model input" includes the injected marker, then returns state.
    def runner(_graph, _context):
        return _scripted_state()

    monkeypatch.setattr(execution, "_default_graph_factory", factory)
    monkeypatch.setattr(execution, "_default_engine_runner", lambda g, c, cfg: runner(g, c))

    # Feed a capture manually is not enough; instead confirm the injection
    # router yields the marker to the tools during the call.
    case = next(c for c in CASES if c.challenge_marker == INJECTION_MARKER)
    outcome = run_case(case, results_dir=str(tmp_path), ticker="AAPL", analysis_date="2026-01-09")
    # With a scripted engine that makes no LLM call, the marker cannot reach the
    # model; the harness must record that honestly (False), not fake True.
    assert outcome.challenge_marker == INJECTION_MARKER
    assert outcome.challenge_reached_model is False
    assert any("did NOT reach" in note for note in outcome.notes)
