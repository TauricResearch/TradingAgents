import json

import pytest

from tradingagents.agents.schemas import DecisionStatus
from tradingagents.evaluation import (
    EvaluationCosts,
    EvaluationObservation,
    ResearchPrediction,
    WalkForwardEvaluator,
    evaluate_prediction,
)


def _prediction(**overrides):
    values = {
        "ticker": "NVDA",
        "analysis_date": "2026-01-02",
        "rating": "Buy",
        "decision_status": DecisionStatus.RESEARCH_COMPLETE.value,
        "horizon_days": 5,
        "expected_return_low": 0.08,
        "expected_return_high": 0.12,
        "confidence": 0.7,
        "benchmark": "SPY",
        "schema_version": "research-decision-v1",
    }
    values.update(overrides)
    return ResearchPrediction(**values)


@pytest.mark.unit
def test_evaluation_computes_costs_alpha_hit_interval_and_adverse_move():
    result = evaluate_prediction(
        _prediction(),
        EvaluationObservation(
            entry_price=100,
            exit_price=110,
            path_prices=[100, 95, 105, 110],
            benchmark_entry_price=100,
            benchmark_exit_price=105,
            observation_date="2026-01-09",
        ),
        costs=EvaluationCosts(transaction_cost_bps=20, slippage_bps=10),
    )
    assert result.actual_return == pytest.approx(0.10)
    assert result.benchmark_excess_return == pytest.approx(0.05)
    assert result.net_direction_adjusted_return == pytest.approx(0.097)
    assert result.net_direction_adjusted_alpha == pytest.approx(0.047)
    assert result.hit is True
    assert result.interval_hit is True
    assert result.max_adverse_excursion == pytest.approx(-0.05)
    assert result.benchmark == "SPY"
    assert result.observation_date == "2026-01-09"
    assert result.entry_price == 100


@pytest.mark.unit
def test_bearish_prediction_uses_rising_price_as_adverse_excursion():
    result = evaluate_prediction(
        _prediction(rating="Sell", expected_return_low=-0.15, expected_return_high=-0.05),
        EvaluationObservation(100, 90, [100, 110, 90]),
    )
    assert result.direction_adjusted_return == pytest.approx(0.10)
    assert result.max_adverse_excursion == pytest.approx(-0.10)
    assert result.hit is True


@pytest.mark.unit
def test_non_actionable_research_is_recorded_but_excluded_from_hit_rate(tmp_path):
    evaluator = WalkForwardEvaluator(tmp_path / "evaluations.jsonl")
    blocked = evaluator.record(
        _prediction(decision_status=DecisionStatus.NO_TRADE.value),
        EvaluationObservation(100, 120, [100, 120]),
    )
    actionable = evaluator.record(
        _prediction(),
        EvaluationObservation(100, 110, [100, 110]),
    )
    summary = evaluator.summarize()
    assert blocked.eligible is False
    assert blocked.hit is None
    assert actionable.hit is True
    assert summary["sample_count"] == 2
    assert summary["eligible_count"] == 1
    assert summary["hit_rate"] == 1.0
    lines = (tmp_path / "evaluations.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["decision_status"] == DecisionStatus.NO_TRADE.value


@pytest.mark.unit
def test_prediction_can_be_created_from_programmatic_research_result():
    prediction = ResearchPrediction.from_research_result(
        {
            "ticker": "AAPL",
            "analysis_date": "2026-01-02",
            "rating": "Underweight",
            "decision_status": DecisionStatus.HUMAN_REVIEW_REQUIRED.value,
            "expected_return_low": -0.1,
            "expected_return_high": 0.02,
            "confidence": 0.5,
            "schema_version": "v1",
        },
        horizon_days=20,
        benchmark="SPY",
    )
    assert prediction.ticker == "AAPL"
    assert prediction.horizon_days == 20
    assert prediction.benchmark == "SPY"


@pytest.mark.unit
def test_cost_assumptions_can_be_loaded_from_project_config():
    costs = EvaluationCosts.from_config({
        "evaluation_transaction_cost_bps": 12,
        "evaluation_slippage_bps": 8,
    })
    assert costs.decimal() == pytest.approx(0.002)
