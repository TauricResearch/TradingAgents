from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from tradingagents.research_platform import (
    BacktestConfig,
    DataProvenance,
    EvidenceRef,
    PriceBar,
    RiskDecision,
    RiskPolicy,
    RiskSeverity,
    TradeDirection,
    TradeHorizon,
    TradeSignal,
    evaluate_basic_risk,
    validate_signal_timing,
)


def _signal(**overrides):
    data = {
        "symbol": "NVDA",
        "as_of_date": date(2026, 1, 5),
        "direction": TradeDirection.BUY,
        "horizon": TradeHorizon.MEDIUM,
        "confidence": 0.75,
        "rationale": "Validated thesis with positive risk/reward.",
        "proposed_position_pct": 0.05,
        "evidence": [
            EvidenceRef(
                source_id="price:NVDA:2026-01-05",
                description="Daily price snapshot",
                as_of_date=date(2026, 1, 5),
                confidence=0.95,
            )
        ],
    }
    data.update(overrides)
    return TradeSignal(**data)


def test_price_bar_requires_consistent_ohlc_range():
    provenance = DataProvenance(
        provider="fixture",
        as_of_date=date(2026, 1, 5),
        retrieved_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )

    bar = PriceBar(
        symbol="NVDA",
        date=date(2026, 1, 5),
        open=100,
        high=105,
        low=99,
        close=104,
        volume=1000,
        provenance=provenance,
    )
    assert bar.provenance.provider == "fixture"

    with pytest.raises(ValidationError):
        PriceBar(
            symbol="NVDA",
            date=date(2026, 1, 5),
            open=110,
            high=105,
            low=99,
            close=104,
            provenance=provenance,
        )


def test_trade_signal_confidence_is_bounded():
    with pytest.raises(ValidationError):
        _signal(confidence=1.2)


def test_backtest_config_rejects_reversed_dates():
    with pytest.raises(ValidationError):
        BacktestConfig(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
            symbols=["NVDA"],
        )


def test_signal_timing_rejects_same_day_execution_by_default():
    signal = _signal()
    with pytest.raises(ValueError):
        validate_signal_timing(signal, date(2026, 1, 5))

    validate_signal_timing(signal, date(2026, 1, 5), allow_same_day=True)
    validate_signal_timing(signal, date(2026, 1, 6))


def test_basic_risk_caps_oversized_signal():
    review = evaluate_basic_risk(
        _signal(proposed_position_pct=0.25),
        RiskPolicy(max_single_position_pct=0.10),
    )

    assert review.decision == RiskDecision.REDUCE
    assert review.approved_position_pct == 0.10
    assert review.breaches[0].rule == "max_single_position_pct"


def test_basic_risk_rejects_low_confidence_signal():
    review = evaluate_basic_risk(
        _signal(confidence=0.30),
        RiskPolicy(min_signal_confidence=0.55),
    )

    assert review.decision == RiskDecision.REJECT
    assert review.approved_position_pct == 0.0
    assert review.breaches[0].rule == "min_signal_confidence"


def test_basic_risk_rejects_when_drawdown_limit_is_breached():
    review = evaluate_basic_risk(
        _signal(),
        RiskPolicy(max_portfolio_drawdown_pct=0.10),
        portfolio_drawdown_pct=0.12,
    )

    assert review.decision == RiskDecision.REJECT
    assert review.approved_position_pct == 0.0
    assert review.breaches[0].rule == "max_portfolio_drawdown_pct"


def test_hold_signal_is_watch_only():
    review = evaluate_basic_risk(
        _signal(direction=TradeDirection.HOLD, proposed_position_pct=None),
        RiskPolicy(),
        current_position_pct=0.04,
    )

    assert review.decision == RiskDecision.WATCH
    assert review.approved_position_pct == 0.04

def test_basic_risk_returns_structured_rule_results():
    review = evaluate_basic_risk(
        _signal(),
        RiskPolicy(max_single_position_pct=0.10),
    )

    assert review.decision == RiskDecision.APPROVE
    assert review.rule_results
    assert all(result.passed for result in review.rule_results)
    assert review.rule_results[0].severity == RiskSeverity.INFO


def test_basic_risk_reduces_for_gross_exposure_budget():
    review = evaluate_basic_risk(
        _signal(proposed_position_pct=0.10),
        RiskPolicy(max_single_position_pct=0.20, max_gross_exposure_pct=0.80),
        portfolio_gross_exposure_pct=0.75,
    )

    assert review.decision == RiskDecision.REDUCE
    assert review.approved_position_pct == pytest.approx(0.05)
    assert review.breaches[-1].rule == "max_gross_exposure_pct"
    assert review.breaches[-1].recommended_action == "reduce_to_available_exposure"


def test_basic_risk_reduces_to_preserve_cash_floor():
    review = evaluate_basic_risk(
        _signal(proposed_position_pct=0.10),
        RiskPolicy(max_single_position_pct=0.20, min_cash_pct=0.95),
        cash_pct=1.0,
    )

    assert review.decision == RiskDecision.REDUCE
    assert review.approved_position_pct == pytest.approx(0.05)
    assert review.breaches[-1].rule == "min_cash_pct"
    assert review.breaches[-1].severity == RiskSeverity.WARNING
