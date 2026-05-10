"""Tests for the Kelly criterion binary position-sizing module."""

import pytest

from tradingagents.agents.schemas import PolymarketDecision, PolymarketDirection
from tradingagents.exchange.binary_risk import kelly_fraction, size_order


def _decision(
    direction: str = "BUY_YES",
    confidence: float = 0.70,
    yes_price: float = 0.40,
) -> PolymarketDecision:
    return PolymarketDecision(
        market_id="540816",
        question="Will X happen by Y date?",
        direction=PolymarketDirection(direction),
        confidence=confidence,
        rationale="synthetic",
        yes_price_at_analysis=yes_price,
        cycle_ts=12345,
    )


# ---------------------------------------------------------------------------
# kelly_fraction — pure math
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_kelly_fraction_positive_ev():
    # p=0.6, b=1.5 → f* = (1.5*0.6 - 0.4) / 1.5 = 0.5/1.5 ≈ 0.333
    f = kelly_fraction(p=0.6, b=1.5)
    assert abs(f - (1.5 * 0.6 - 0.4) / 1.5) < 1e-9


@pytest.mark.unit
def test_kelly_fraction_negative_ev():
    # p=0.3, b=1.0 → f* = (1.0*0.3 - 0.7)/1.0 = -0.4 (don't bet)
    f = kelly_fraction(p=0.3, b=1.0)
    assert f < 0


@pytest.mark.unit
def test_kelly_fraction_break_even():
    # p=0.5, b=1.0 → f* = 0 exactly (fair odds)
    f = kelly_fraction(p=0.5, b=1.0)
    assert abs(f) < 1e-9


# ---------------------------------------------------------------------------
# size_order — full pipeline
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_hold_returns_zero():
    result = size_order(_decision(direction="HOLD"), capital_usd=1000.0)
    assert result["fraction"] == 0.0
    assert result["usd"] == 0.0
    assert "HOLD" in result["reason"]


@pytest.mark.unit
def test_below_min_confidence_returns_zero():
    result = size_order(_decision(confidence=0.54), capital_usd=1000.0, min_confidence=0.55)
    assert result["fraction"] == 0.0
    assert result["usd"] == 0.0
    assert "confidence" in result["reason"].lower()


@pytest.mark.unit
def test_negative_kelly_returns_zero():
    # confidence=0.56 (just above threshold), yes_price=0.70 → b=(1/0.70)-1≈0.43
    # f* = (0.43*0.56 - 0.44)/0.43 < 0
    result = size_order(_decision(confidence=0.56, yes_price=0.70), capital_usd=1000.0)
    assert result["fraction"] == 0.0
    assert "negative" in result["reason"].lower()


@pytest.mark.unit
def test_buy_yes_normal_case():
    # yes_price=0.40, confidence=0.70
    # b = (1/0.40) - 1 = 1.5
    # f* = (1.5*0.70 - 0.30) / 1.5 = 0.75/1.5 = 0.50
    # half-Kelly → 0.25, capped at 0.20 → max_fraction applies
    result = size_order(
        _decision(direction="BUY_YES", confidence=0.70, yes_price=0.40),
        capital_usd=1000.0,
        max_fraction=0.20,
        kelly_multiplier=0.5,
    )
    assert result["fraction"] == pytest.approx(0.20)
    assert result["usd"] == pytest.approx(200.0)
    assert "capped" in result["reason"].lower()


@pytest.mark.unit
def test_buy_no_normal_case():
    # yes_price=0.40 → no_price=0.60, b=(1/0.60)-1≈0.667
    # f* = (0.667*0.70 - 0.30)/0.667 ≈ 0.25
    # half-Kelly → 0.125, below cap of 0.20 → 0.125
    result = size_order(
        _decision(direction="BUY_NO", confidence=0.70, yes_price=0.40),
        capital_usd=1000.0,
        max_fraction=0.20,
        kelly_multiplier=0.5,
    )
    assert result["fraction"] == pytest.approx(0.125, rel=0.01)
    assert result["usd"] == pytest.approx(125.0, rel=0.01)
    assert "capped" not in result["reason"].lower()


@pytest.mark.unit
def test_half_kelly_multiplier_applied():
    r1 = size_order(
        _decision(direction="BUY_NO", confidence=0.70, yes_price=0.40),
        capital_usd=1000.0,
        max_fraction=1.0,
        kelly_multiplier=1.0,
    )
    r05 = size_order(
        _decision(direction="BUY_NO", confidence=0.70, yes_price=0.40),
        capital_usd=1000.0,
        max_fraction=1.0,
        kelly_multiplier=0.5,
    )
    assert r05["fraction"] == pytest.approx(r1["fraction"] * 0.5, rel=0.01)


@pytest.mark.unit
def test_max_fraction_cap_enforced():
    result = size_order(
        _decision(direction="BUY_YES", confidence=0.95, yes_price=0.10),
        capital_usd=1000.0,
        max_fraction=0.05,
        kelly_multiplier=1.0,
    )
    assert result["fraction"] == pytest.approx(0.05)
    assert "capped" in result["reason"].lower()


@pytest.mark.unit
def test_usd_scales_with_capital():
    r_small = size_order(_decision(), capital_usd=500.0)
    r_large = size_order(_decision(), capital_usd=2000.0)
    if r_small["fraction"] > 0:
        assert r_large["usd"] == pytest.approx(r_small["usd"] * 4, rel=0.01)
