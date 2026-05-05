import pytest

from tradingagents.agents.utils.trade_filter import compute_trade_filter, compute_trade_filter_score


@pytest.mark.unit
def test_trade_filter_low_when_missing_levels():
    score, reasons = compute_trade_filter_score(
        trade_levels=None,
        rating="Buy",
        rm_rating="Buy",
        trader_action="Buy",
        data_quality="high",
        error_count=0,
        structured_valid=True,
    )
    assert score < 0.4
    assert reasons


@pytest.mark.unit
def test_trade_filter_higher_in_trend_with_good_quality():
    levels = {
        "regime": "trend",
        "regime_confidence": 0.8,
        "bias": "long",
        "anchors": {"atr_pct": 0.02, "trend_strength": 0.04},
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "rr_target": 2.0,
    }
    score, _ = compute_trade_filter_score(
        trade_levels=levels,
        rating="Buy",
        rm_rating="Buy",
        trader_action="Buy",
        data_quality="high",
        error_count=0,
        structured_valid=True,
    )
    assert score > 0.6


@pytest.mark.unit
def test_trade_filter_hard_reject_rr_too_low():
    levels = {
        "regime": "trend",
        "regime_confidence": 0.8,
        "bias": "long",
        "anchors": {"atr_pct": 0.02, "trend_strength": 0.04},
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 101.0,
        "rr_target": 1.1,
        "entry_condition": "Trend long (confirmation): wait for close above ... then retest ...",
    }
    result = compute_trade_filter(
        trade_levels=levels,
        rating="Buy",
        rm_rating="Buy",
        trader_action="Buy",
        data_quality="high",
        error_count=0,
        structured_valid=True,
        threshold=0.65,
    )
    assert result["hard_reject"] is True
    assert result["filtered_out"] is True
    assert result["pass"] is False
    assert any("RR target too low" in r for r in result["hard_reject_reasons"])
