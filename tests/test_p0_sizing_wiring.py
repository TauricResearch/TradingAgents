"""P0.5 wiring: exposure-capped sizing runs in the real flow.

The plan's numbers (entry/stop/ATR/direction) are extracted
deterministically from the Trader's own plan text — labelled patterns
only, bare numbers in prose never guessed — and the sizing applies the
stop-distance budget AND the per-symbol exposure cap simultaneously.
Without portfolio context no size is invented.
"""

from __future__ import annotations

import json

import pytest

from tradingagents.dataflows.plan_extraction import extract_plan_numbers


class TestPlanExtraction:
    def test_labelled_numbers_are_extracted(self):
        plan = "Entry 560.00, stop 552.07, ATR 8.0. Long on weakness."
        numbers = extract_plan_numbers(plan)
        assert numbers.entry == pytest.approx(560.0)
        assert numbers.stop == pytest.approx(552.07)
        assert numbers.atr == pytest.approx(8.0)
        assert numbers.direction == "LONG"
        assert numbers.has_plan

    def test_labelled_with_colon_and_dollar(self):
        plan = "Entry: $560 | stop-loss: $552.07 | ATR(14): 8"
        numbers = extract_plan_numbers(plan)
        assert numbers.entry == pytest.approx(560.0)
        assert numbers.stop == pytest.approx(552.07)
        assert numbers.atr == pytest.approx(8.0)

    def test_short_direction_is_detected(self):
        plan = "Short entry 560, stop 568, ATR 8."
        numbers = extract_plan_numbers(plan)
        assert numbers.direction == "SHORT"
        assert numbers.has_plan

    def test_bare_numbers_are_never_guessed(self):
        """A plan that mentions prices without labels extracts nothing."""
        plan = "The stock traded between 557 and 562 on Friday."
        numbers = extract_plan_numbers(plan)
        assert numbers.entry is None
        assert numbers.stop is None
        assert not numbers.has_plan

    def test_empty_text_extracts_nothing(self):
        assert extract_plan_numbers("").entry is None
        assert extract_plan_numbers(None).stop is None

    def test_comma_decimal_is_normalized(self):
        plan = "Entry 14,20, stop 13,80, ATR 0,30"
        numbers = extract_plan_numbers(plan)
        assert numbers.entry == pytest.approx(14.20)
        assert numbers.stop == pytest.approx(13.80)


class TestSizingWiring:
    def _state(self, plan_text="", rating="Overweight"):
        return {
            "company_of_interest": "BRK-B",
            "trade_date": "2026-11-08",
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {"bull_history": "", "bear_history": "",
                                        "history": "", "current_response": ""},
            "trader_investment_plan": plan_text,
            "risk_debate_state": {"aggressive_history": "", "conservative_history": "",
                                  "neutral_history": "", "history": ""},
            "investment_plan": "",
            "final_rating": rating,
            "final_trade_decision": f"**Rating**: {rating}\nPlan.",
        }

    def test_the_capped_size_reaches_the_audit(self, tmp_path):
        """The 100k/1%/560/552.07/5%-cap scenario: 8 shares in the audit."""
        from tradingagents.dataflows.gate_integration import (
            evaluate_decision,
            write_audit_record,
        )

        state = self._state(
            plan_text="Entry 560.00, stop 552.07, ATR 8.0. Long on weakness."
        )
        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08", state, snapshot_id="s1",
            equity=100_000.0, cash=100_000.0, risk_budget=1_000.0,
            max_symbol_exposure=0.05,
        )
        assert record.exposure_sizing is not None
        assert record.exposure_sizing.qty == 8
        assert record.exposure_sizing.notional == pytest.approx(4_480.0)
        assert record.exposure_sizing.binding_constraint == "EXPOSURE_CAP"

        path = write_audit_record(record, str(tmp_path))
        data = json.loads(path.read_text(encoding="utf-8"))
        risk = data["risk"]
        assert risk["exposure_capped_qty"] == 8
        assert risk["exposure_binding_constraint"] == "EXPOSURE_CAP"
        assert risk["exposure_cap_applied"] is True

    def test_missing_portfolio_context_blocks_the_sized_plan(self):
        """A plan with numbers but no equity: no size is invented, BLOCK —
        and the audit records WHY the sizing could not run."""
        from tradingagents.dataflows.gate_integration import evaluate_decision

        state = self._state(
            plan_text="Entry 560.00, stop 552.07, ATR 8.0. Long."
        )
        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08", state, snapshot_id="s1",
            equity=None, risk_budget=1_000.0, max_symbol_exposure=0.05,
        )
        # The sizing result is kept with its reason: the audit shows the
        # plan could not be sized for lack of portfolio context.
        assert record.exposure_sizing is not None
        assert record.exposure_sizing.qty == 0
        assert "PORTFOLIO_CONTEXT_MISSING" in [
            r.value for r in record.exposure_sizing.reasons
        ]
        assert decision.action.value == "BLOCK"

    def test_a_plan_without_numbers_skips_the_risk_check(self):
        """No extractable numbers: the risk check is skipped, not guessed."""
        from tradingagents.dataflows.gate_integration import evaluate_decision

        state = self._state(plan_text="Accumulate on weakness toward the band.")
        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08", state, snapshot_id="s1",
            equity=100_000.0, risk_budget=1_000.0, max_symbol_exposure=0.05,
        )
        assert record.exposure_sizing is None
        assert record.stop_validation is None

    def test_a_wrong_side_stop_blocks_through_the_real_path(self):
        """A LONG plan whose stop sits above the entry: BLOCK."""
        from tradingagents.dataflows.gate_integration import evaluate_decision

        state = self._state(
            plan_text="Entry 560.00, stop 568.00, ATR 8.0. Long."
        )
        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08", state, snapshot_id="s1",
            equity=100_000.0, risk_budget=1_000.0, max_symbol_exposure=0.05,
        )
        assert decision.action.value == "BLOCK"
        reasons = [r.value for r in decision.reasons]
        assert "RISK_PLAN_BLOCKED" in reasons

    def test_a_short_plan_uses_its_own_side(self):
        from tradingagents.dataflows.gate_integration import evaluate_decision

        state = self._state(
            plan_text="Short entry 560.00, stop 568.00, ATR 8.0."
        )
        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08", state, snapshot_id="s1",
            equity=100_000.0, risk_budget=1_000.0, max_symbol_exposure=0.05,
        )
        assert record.exposure_sizing is not None
        assert record.exposure_sizing.qty > 0
        assert not record.exposure_sizing.blocked
