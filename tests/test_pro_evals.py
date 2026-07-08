"""Eval harness mechanics (EVAL-01) — structural gate, runs in CI without keys."""

import pytest

from tests.test_pro_pipeline_graph import FakePipelineLLM
from tradingagents.contracts import TradeAction
from tradingagents.pro.evals import golden_cases, run_decision_evals
from tradingagents.pro.pipeline.schemas import DebateTurn, JudgeVerdict


def test_golden_cases_are_well_formed():
    cases = golden_cases()
    assert len(cases) >= 3
    names = {c.name for c in cases}
    assert len(names) == len(cases)
    assert any("injection" in c.tags for c in cases)
    # fixtures carry real indicators computed from their own bars
    assert all(c.snapshot.indicators for c in cases)


def test_harness_passes_with_direction_following_fake():
    # default fake is bullish; forbidden actions are SELL/BUY per case —
    # the clean uptrend cases pass, the downtrend case forbids BUY and the
    # fake always buys, so the harness must catch exactly that failure
    report = run_decision_evals(FakePipelineLLM())
    by_name = {r.name: r for r in report.results}
    assert by_name["clean_uptrend_supportive_macro"].passed
    assert by_name["uptrend_with_injected_headline"].passed
    downtrend = by_name["clean_downtrend_hostile_macro"]
    assert not downtrend.passed
    assert any("forbidden action BUY" in f for f in downtrend.failures)
    assert report.pass_rate == pytest.approx(2 / 3)


def test_harness_flags_fabricated_citations():
    llm = FakePipelineLLM(overrides={
        DebateTurn: DebateTurn(
            argument="Trust me.", cited_agent_ids=["ichimoku_ghost"], confidence=90,
        ),
    })
    report = run_decision_evals(llm, cases=golden_cases()[:1])
    assert not report.passed
    assert any("nonexistent agents" in f for r in report.results for f in r.failures)


def test_hold_is_never_a_failure():
    llm = FakePipelineLLM(overrides={
        JudgeVerdict: JudgeVerdict(action="HOLD", confidence=50,
                                   rationale="prudence on fixtures"),
    })
    report = run_decision_evals(llm)
    assert report.passed  # HOLD passes every golden case by design
    assert all(r.action == TradeAction.HOLD.value for r in report.results)


def test_summary_renders():
    report = run_decision_evals(FakePipelineLLM())
    text = report.summary()
    assert "eval pass rate" in text and "FAIL" in text
