"""Tests for PMDecisionSchema Pydantic structured output model.

Covers:
- Valid payload parses correctly
- Invalid enum values raise ValidationError
- Required fields enforce presence
- JSON round-trip fidelity
- Type coercion behaviour (SellOrder.macro_driven bool coercion)
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from tradingagents.agents.portfolio.pm_decision_agent import (
    BuyOrder,
    ForensicReport,
    HoldOrder,
    PMDecisionSchema,
    SellOrder,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_payload() -> dict:
    """Return a fully valid PMDecisionSchema payload."""
    return {
        "macro_regime": "risk-off",
        "regime_alignment_note": "Elevated VIX supports defensive posture",
        "sells": [
            {
                "ticker": "AAPL",
                "shares": 10.0,
                "rationale": "Overvalued",
                "macro_driven": True,
            }
        ],
        "buys": [
            {
                "ticker": "XOM",
                "shares": 5.0,
                "price_target": 120.0,
                "stop_loss": 108.0,
                "take_profit": 138.0,
                "sector": "Energy",
                "rationale": "Energy tailwind",
                "thesis": "Oil cycle upswing",
                "macro_alignment": "Fits risk-off energy play",
                "memory_note": "XOM held well in last risk-off",
                "position_sizing_logic": "2% position; below 15% cap",
            }
        ],
        "holds": [{"ticker": "MSFT", "rationale": "Thesis intact"}],
        "cash_reserve_pct": 0.1,
        "portfolio_thesis": "Defensive tilt with energy exposure",
        "risk_summary": "Moderate risk; elevated VIX",
        "forensic_report": {
            "regime_alignment": "risk-off favours energy and cash",
            "key_risks": ["oil demand drop", "rate surprise"],
            "decision_confidence": "high",
            "position_sizing_rationale": "All positions within 15% cap",
        },
    }


# ---------------------------------------------------------------------------
# TestPMDecisionSchema — valid payloads
# ---------------------------------------------------------------------------


class TestPMDecisionSchema:
    def test_valid_payload_parses(self):
        """A valid payload produces a PMDecisionSchema instance."""
        obj = PMDecisionSchema(**_valid_payload())
        assert obj.macro_regime == "risk-off"
        assert len(obj.buys) == 1
        assert obj.forensic_report.decision_confidence == "high"

    def test_macro_regime_all_valid_values(self):
        """Each of the four valid macro_regime values parses correctly."""
        for regime in ("risk-on", "risk-off", "neutral", "transition"):
            payload = _valid_payload()
            payload["macro_regime"] = regime
            obj = PMDecisionSchema(**payload)
            assert obj.macro_regime == regime

    def test_invalid_macro_regime_raises(self):
        """Invalid macro_regime value raises ValidationError."""
        payload = _valid_payload()
        payload["macro_regime"] = "unknown"
        with pytest.raises(ValidationError):
            PMDecisionSchema(**payload)

    def test_empty_string_macro_regime_raises(self):
        """Empty string macro_regime raises ValidationError."""
        payload = _valid_payload()
        payload["macro_regime"] = ""
        with pytest.raises(ValidationError):
            PMDecisionSchema(**payload)

    def test_invalid_decision_confidence_raises(self):
        """Invalid decision_confidence in forensic_report raises ValidationError."""
        payload = _valid_payload()
        payload["forensic_report"]["decision_confidence"] = "very high"
        with pytest.raises(ValidationError):
            PMDecisionSchema(**payload)

    def test_decision_confidence_all_valid_values(self):
        """Each of the three valid decision_confidence values parses correctly."""
        for level in ("high", "medium", "low"):
            payload = _valid_payload()
            payload["forensic_report"]["decision_confidence"] = level
            obj = PMDecisionSchema(**payload)
            assert obj.forensic_report.decision_confidence == level

    def test_missing_forensic_report_raises(self):
        """Missing forensic_report field raises ValidationError."""
        payload = _valid_payload()
        del payload["forensic_report"]
        with pytest.raises(ValidationError):
            PMDecisionSchema(**payload)

    def test_missing_macro_regime_raises(self):
        """Missing macro_regime field raises ValidationError."""
        payload = _valid_payload()
        del payload["macro_regime"]
        with pytest.raises(ValidationError):
            PMDecisionSchema(**payload)

    def test_model_dump_json_roundtrip(self):
        """model_dump_json() produces valid JSON that round-trips back."""
        obj = PMDecisionSchema(**_valid_payload())
        json_str = obj.model_dump_json()
        data = json.loads(json_str)
        assert data["macro_regime"] == "risk-off"
        assert data["forensic_report"]["decision_confidence"] == "high"

    def test_sell_order_macro_driven_bool(self):
        """SellOrder.macro_driven must be a boolean (Pydantic v2 coerces str)."""
        payload = _valid_payload()
        payload["sells"][0]["macro_driven"] = "yes"  # string — Pydantic v2 coerces
        obj = PMDecisionSchema(**payload)
        assert isinstance(obj.sells[0].macro_driven, bool)

    def test_empty_sells_buys_holds_allowed(self):
        """Sells, buys, and holds can all be empty lists."""
        payload = _valid_payload()
        payload["sells"] = []
        payload["buys"] = []
        payload["holds"] = []
        obj = PMDecisionSchema(**payload)
        assert obj.sells == []
        assert obj.buys == []
        assert obj.holds == []

    def test_multiple_buys_parsed(self):
        """Multiple BuyOrder entries in buys list all parse correctly."""
        payload = _valid_payload()
        extra_buy = {
            "ticker": "CVX",
            "shares": 3.0,
            "price_target": 160.0,
            "stop_loss": 144.0,
            "take_profit": 184.0,
            "sector": "Energy",
            "rationale": "CVX undervalued",
            "thesis": "Same oil cycle thesis",
            "macro_alignment": "Energy fits risk-off",
            "memory_note": "CVX volatile in past cycles",
            "position_sizing_logic": "1.5% position",
        }
        payload["buys"].append(extra_buy)
        obj = PMDecisionSchema(**payload)
        assert len(obj.buys) == 2
        assert obj.buys[1].ticker == "CVX"

    def test_cash_reserve_pct_stored_as_float(self):
        """cash_reserve_pct is preserved as a float."""
        payload = _valid_payload()
        payload["cash_reserve_pct"] = 0.15
        obj = PMDecisionSchema(**payload)
        assert obj.cash_reserve_pct == 0.15


# ---------------------------------------------------------------------------
# TestForensicReport
# ---------------------------------------------------------------------------


class TestForensicReport:
    def test_valid_forensic_report(self):
        """ForensicReport validates correctly with all required fields."""
        report = ForensicReport(
            regime_alignment="risk-off supports cash",
            key_risks=["rate spike", "credit crunch"],
            decision_confidence="medium",
            position_sizing_rationale="All within 10% cap",
        )
        assert report.decision_confidence == "medium"
        assert len(report.key_risks) == 2

    def test_key_risks_can_be_empty(self):
        """key_risks list can be empty."""
        report = ForensicReport(
            regime_alignment="aligned",
            key_risks=[],
            decision_confidence="low",
            position_sizing_rationale="cautious",
        )
        assert report.key_risks == []


# ---------------------------------------------------------------------------
# TestBuyOrder
# ---------------------------------------------------------------------------


class TestBuyOrder:
    def test_valid_buy_order(self):
        """BuyOrder validates with all required fields."""
        order = BuyOrder(
            ticker="NVDA",
            shares=2.0,
            price_target=900.0,
            stop_loss=810.0,
            take_profit=1080.0,
            sector="Technology",
            rationale="AI demand surge",
            thesis="GPU dominance continues",
            macro_alignment="Neutral regime allows tech exposure",
            memory_note="NVDA strong in prior neutral regimes",
            position_sizing_logic="1% position",
        )
        assert order.ticker == "NVDA"
        assert order.price_target == 900.0


# ---------------------------------------------------------------------------
# TestSellOrder
# ---------------------------------------------------------------------------


class TestSellOrder:
    def test_valid_sell_order(self):
        """SellOrder validates with all required fields."""
        order = SellOrder(
            ticker="TSLA",
            shares=5.0,
            rationale="Overextended rally",
            macro_driven=False,
        )
        assert order.ticker == "TSLA"
        assert order.macro_driven is False


# ---------------------------------------------------------------------------
# TestHoldOrder
# ---------------------------------------------------------------------------


class TestHoldOrder:
    def test_valid_hold_order(self):
        """HoldOrder validates with required fields."""
        order = HoldOrder(ticker="AMZN", rationale="Cloud thesis intact")
        assert order.ticker == "AMZN"
