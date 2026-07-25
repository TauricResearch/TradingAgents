from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradingagents.evaluation.contradictions import (
    DecisionEvaluationCase,
    evaluate_contradictions,
    load_eval_cases,
    require_no_contradiction,
)
from tradingagents.evaluation.source_alignment import (
    SourceSignal,
    project_source_alignment,
    render_source_alignment_summary,
    source_alignment_from_ledger,
)


def test_source_alignment_exposes_directional_consensus_and_divergence():
    bullish = project_source_alignment([SourceSignal("official", 0.8), SourceSignal("wire", 0.5)])
    assert bullish.label == "Bullish"
    assert bullish.bullish_percent == 1.0

    divergent = project_source_alignment([SourceSignal("bull", 0.9), SourceSignal("bear", -0.8)])
    assert divergent.label == "Wide divergence"
    assert divergent.score_range == pytest.approx(1.7)


def test_contradiction_gate_sets_score_to_zero_and_fixture_models_are_separate():
    path = Path(__file__).parent / "evals" / "contradictions.csv"
    cases = load_eval_cases(path)
    results = {case.case_id: evaluate_contradictions(case) for case in cases}
    assert results["bullish-buy"].score == 1.0
    assert results["contradictory-bull"].score == 0.0
    assert results["contradictory-bull"].reasons == ("bullish_thesis_with_sell_action",)
    with pytest.raises(ValueError, match="contradiction gate failed"):
        require_no_contradiction(next(case for case in cases if case.case_id == "contradictory-bull"))


def test_judge_model_must_not_equal_target_model():
    with pytest.raises(ValueError, match="judge_model must differ"):
        DecisionEvaluationCase("bad", "bullish", "buy", True, "same", "same")


def test_source_alignment_from_ledger_reads_direction_scores_and_skips_unscored():
    ledger = {
        "evidence": [
            {"source_provider": "official", "direction_score": 0.8},
            {"source_provider": "wire", "direction_score": -0.6},
            {"source_provider": "unscored"},
            {"source_provider": "invalid", "direction_score": "not a number"},
        ]
    }
    alignment = source_alignment_from_ledger(ledger)
    assert alignment is not None
    assert alignment.label == "Wide divergence"
    assert alignment.source_count == 2


def test_source_alignment_from_ledger_returns_none_without_direction_scores():
    ledger = {"evidence": [{"source_provider": "official"}, {"source_provider": "wire"}]}
    assert source_alignment_from_ledger(ledger) is None


def test_render_source_alignment_summary_is_none_without_directional_evidence():
    assert render_source_alignment_summary({"evidence": [{"source_provider": "x"}]}) is None


def test_render_source_alignment_summary_includes_label_and_direction_split():
    ledger = {
        "evidence": [
            {"source_provider": "official", "direction_score": 0.8},
            {"source_provider": "wire", "direction_score": -0.6},
        ]
    }
    summary = render_source_alignment_summary(ledger)
    assert summary is not None
    assert "label=Wide divergence" in summary
    assert "sources=2" in summary
    assert "bullish=50%" in summary
    assert "bearish=50%" in summary


def _researcher_state(ledger: dict) -> dict:
    return {
        "company_of_interest": "AAPL",
        "instrument_context": "Ticker: AAPL; Apple Inc.",
        "asset_type": "stock",
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
        "evidence_ledger": ledger,
    }


def _capturing_llm(captured: dict) -> MagicMock:
    llm = MagicMock()
    llm.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or MagicMock(content="argument")
    )
    return llm


@pytest.mark.parametrize("role", ["bull", "bear"])
def test_researcher_prompt_includes_alignment_when_ledger_has_directions(role: str):
    from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

    factory = create_bull_researcher if role == "bull" else create_bear_researcher
    captured: dict = {}
    ledger = {
        "evidence": [
            {"source_provider": "official", "direction_score": 0.8},
            {"source_provider": "wire", "direction_score": -0.6},
        ]
    }
    factory(_capturing_llm(captured))(_researcher_state(ledger))
    assert "Evidence source alignment:" in captured["prompt"]
    assert "Wide divergence" in captured["prompt"]


@pytest.mark.parametrize("role", ["bull", "bear"])
def test_researcher_prompt_omits_alignment_when_ledger_has_no_directions(role: str):
    from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

    factory = create_bull_researcher if role == "bull" else create_bear_researcher
    captured: dict = {}
    factory(_capturing_llm(captured))(
        _researcher_state({"evidence": [{"source_provider": "official"}]})
    )
    assert "Evidence source alignment:" not in captured["prompt"]
