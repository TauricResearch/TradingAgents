"""Eval harness mechanics (EVAL-01) — structural gate, runs in CI without keys."""

import pytest

from tests.test_pro_pipeline_graph import FakePipelineLLM
from tradingagents.contracts import TradeAction
from tradingagents.pro.evals import golden_cases, run_decision_evals
from tradingagents.pro.evals.harness import wilson_interval
from tradingagents.pro.pipeline.schemas import DebateTurn, JudgeVerdict


def test_golden_set_shape_and_coverage():
    cases = golden_cases()
    assert len(cases) >= 15
    names = [c.name for c in cases]
    assert len(names) == len(set(names))
    tags = {t for c in cases for t in c.tags}
    assert {"direction", "ambiguous", "injection", "intraday", "gap"} <= tags
    assert sum(1 for c in cases if "injection" in c.tags) >= 5
    # both failure modes are represented
    assert any(TradeAction.BUY in c.forbidden_actions for c in cases)
    assert any(TradeAction.SELL in c.forbidden_actions for c in cases)
    assert any(c.max_directional_confidence is not None for c in cases)
    # fixtures carry real indicators computed from their own bars
    assert all(c.snapshot.indicators for c in cases)
    # HOLD is never forbidden
    assert all(TradeAction.HOLD not in c.forbidden_actions for c in cases)


def test_harness_scores_the_always_buy_fake_correctly():
    """The fake always rules BUY@72: BUY-forbidding cases must fail,
    SELL-forbidding cases pass, and ambiguous cases with caps below 72
    must flag overconfidence."""
    report = run_decision_evals(FakePipelineLLM())
    by_name = {s.name: s for s in report.sampled}
    for case in golden_cases():
        result = by_name[case.name].runs[0]
        if TradeAction.BUY in case.forbidden_actions:
            assert not result.passed, case.name
            assert any("forbidden action BUY" in f for f in result.failures)
        elif (case.max_directional_confidence is not None
              and case.max_directional_confidence < 72):
            assert any("overconfident" in f for f in result.failures), case.name
        elif TradeAction.SELL in case.forbidden_actions:
            assert result.passed, (case.name, result.failures)


def test_n_samples_and_consistency():
    report = run_decision_evals(FakePipelineLLM(), samples=3,
                                cases=golden_cases()[:2])
    assert len(report.results) == 6
    for sampled in report.sampled:
        assert len(sampled.runs) == 3
        assert sampled.consistency == 1.0  # deterministic fake
    assert "x 3 samples" in report.summary()
    assert "95% CI" in report.summary()


def test_flaky_outcomes_reduce_consistency_and_fail_the_case():
    """Judge alternates HOLD@50 / BUY@90 on the sideways-chop fixture
    (confidence cap 70): the BUY@90 samples are overconfidence failures,
    consistency drops to 0.5, and one bad sample fails the whole case."""

    class Alternating(FakePipelineLLM):
        def __init__(self):
            super().__init__()
            self.n = 0

        def with_structured_output(self, schema):
            if schema is JudgeVerdict:
                self.n += 1
                verdict = (
                    JudgeVerdict(action="BUY", confidence=90, rationale="conviction")
                    if self.n % 2 == 0
                    else JudgeVerdict(action="HOLD", confidence=50, rationale="chop")
                )
                self.overrides = {JudgeVerdict: verdict}
            return super().with_structured_output(schema)

    chop = [c for c in golden_cases() if c.name == "sideways_chop"]
    report = run_decision_evals(Alternating(), samples=4, cases=chop)
    sampled = report.sampled[0]
    assert sampled.consistency == 0.5  # HOLD, BUY, HOLD, BUY
    assert sampled.pass_rate == 0.5  # BUY@90 breaches the ambiguity cap
    assert not sampled.passed  # any failing sample fails the case
    assert any("overconfident BUY@90" in f
               for r in sampled.runs for f in r.failures)


def test_unsupported_ruling_is_caught_by_the_pm_gate_not_the_harness():
    """A SELL ruling over all-bullish fake evidence dies at the portfolio
    manager (no supporting evidence) — a reasoned rejection, which the
    harness rightly treats as a pass, not a forbidden action."""
    llm = FakePipelineLLM(overrides={
        JudgeVerdict: JudgeVerdict(action="SELL", confidence=80, rationale="contrarian"),
    })
    uptrend = [c for c in golden_cases() if c.name == "clean_uptrend_supportive_macro"]
    report = run_decision_evals(llm, cases=uptrend)
    (result,) = report.results
    assert result.passed
    assert result.rejected_at == "portfolio_manager"
    assert any("no evidence supports" in r for r in result.rejection_reasons)


def test_tag_filter_and_validation():
    report = run_decision_evals(FakePipelineLLM(), tag="injection")
    assert all("injection" in s.case.tags for s in report.sampled)
    assert len(report.sampled) >= 5
    with pytest.raises(ValueError, match="no golden cases tagged"):
        run_decision_evals(FakePipelineLLM(), tag="nonexistent")
    with pytest.raises(ValueError, match="samples"):
        run_decision_evals(FakePipelineLLM(), samples=0)


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


def test_wilson_interval_known_values():
    low, high = wilson_interval(90, 100)
    assert 0.82 < low < 0.87 and 0.93 < high < 0.96
    assert wilson_interval(0, 0) == (0.0, 1.0)
    low_all, high_all = wilson_interval(10, 10)
    assert high_all == 1.0 and low_all > 0.65


def test_injection_subset_reported():
    text = run_decision_evals(FakePipelineLLM()).summary()
    assert "injection subset:" in text
