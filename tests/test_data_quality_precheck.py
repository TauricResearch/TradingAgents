"""The data-quality pre-check blocks before the managers conclude.

The 22:56 report was debated in full on a stale filing and contradicted
percentages; only the *order* would have been blocked at the end, which
leaves the analysis — and the repeated Portfolio Manager decision — wrong.

These tests pin the pre-check: it computes the same verdicts as the
Execution Gate, before synthesis, and the gate reuses them so the two
stages cannot disagree.
"""

from __future__ import annotations

import contextlib

from tradingagents.dataflows.data_gate import (
    precheck_data_quality,
    precheck_notice_from_state,
)
from tradingagents.dataflows.filing_freshness import FilingRecord
from tradingagents.graph.data_quality_node import create_data_quality_check

Q2 = FilingRecord("2026-Q2", "2026-06-30", published_date="2026-08-02",
                  filing_date="2026-08-07", form_type="10-Q")
Q3 = FilingRecord("2026-Q3", "2026-09-30", published_date="2026-11-07",
                  form_type="8-K")


class TestPrecheckVerdicts:
    def test_stale_fundamentals_and_wrong_arithmetic_are_both_named(self):
        precheck = precheck_data_quality(
            trade_date="2026-11-08",
            filings=[Q2, Q3],
            used_fundamentals_period_end="2026-06-30",
            used_fundamentals_period="2026-Q2",
            price_snapshot={"close": 570.89, "price_as_of": "2026-11-06",
                            "indicator_as_of": "2026-11-06",
                            "indicator": "52w_high"},
            stated_percentages={
                "distance_from_52w_high": {"stated_pct": -11.3,
                                           "reference": 586.30},
            },
        )
        assert precheck.blocks_execution
        assert "FUNDAMENTALS_STALE" in precheck.blocking_codes
        assert "ARITHMETIC_MISMATCH" in precheck.blocking_codes

        notice = precheck.notice()
        assert "Fundamentals are not current" in notice
        assert "2026-Q3" in notice          # names the period that was missed
        assert "Arithmetic does not support" in notice
        assert "-2.63" in notice            # names the computed figure

    def test_a_clean_run_produces_no_notice(self):
        precheck = precheck_data_quality(
            trade_date="2026-11-08",
            filings=[Q2, Q3],
            used_fundamentals_period_end="2026-09-30",
            price_snapshot={"close": 570.89, "price_as_of": "2026-11-06",
                            "indicator_as_of": "2026-11-06",
                            "indicator": "52w_high"},
            stated_percentages={
                "distance_from_52w_high": {"stated_pct": -2.63,
                                           "reference": 586.30},
            },
        )
        assert not precheck.blocks_execution
        assert precheck.notice() == ""

    def test_before_the_release_q2_is_current_and_silent(self):
        precheck = precheck_data_quality(
            trade_date="2026-11-06",
            filings=[Q2, Q3],
            used_fundamentals_period_end="2026-06-30",
        )
        assert not precheck.blocks_execution
        assert precheck.notice() == ""

    def test_no_filings_known_is_not_a_silent_pass(self):
        precheck = precheck_data_quality(
            trade_date="2026-11-08", filings=[],
            used_fundamentals_period_end="2026-06-30",
        )
        assert precheck.blocks_execution
        assert "FUNDAMENTALS_UNAVAILABLE" in precheck.blocking_codes

    def test_mismatched_price_and_indicator_sessions_are_named(self):
        precheck = precheck_data_quality(
            trade_date="2026-11-08",
            price_snapshot={"close": 570.89, "price_as_of": "2026-11-06",
                            "indicator_as_of": "2026-11-05",
                            "indicator": "SMA200"},
        )
        assert precheck.blocks_execution
        assert "PRICE_TIMESTAMP_MISMATCH" in precheck.blocking_codes


class TestPrecheckNode:
    def _state(self, **overrides):
        state = {
            "company_of_interest": "BRK-B",
            "trade_date": "2026-11-08",
            "fundamentals_report": "Equity: 747910 USD million as of 2026-Q2.",
        }
        state.update(overrides)
        return state

    def test_the_node_records_the_verdicts_and_the_notice(self):
        node = create_data_quality_check(
            filings_provider=lambda ticker, date: [Q2, Q3]
        )
        out = node(self._state())
        precheck = out["data_quality_precheck"]
        assert precheck["blocks_execution"] is True
        assert "FUNDAMENTALS_STALE" in precheck["blocking_codes"]
        assert "Fundamentals are not current" in precheck["notice"]

    def test_a_failing_provider_is_not_a_pass(self):
        def boom(ticker, date):
            raise RuntimeError("SEC down")

        node = create_data_quality_check(filings_provider=boom)
        out = node(self._state())
        # No filings from a broken source -> UNAVAILABLE, never silent.
        assert out["data_quality_precheck"]["blocks_execution"] is True

    def test_a_clean_state_yields_an_empty_notice(self):
        node = create_data_quality_check(
            filings_provider=lambda ticker, date: [Q2, Q3]
        )
        out = node(self._state(
            fundamentals_report="Equity: 761368 USD million as of 2026-Q3."
        ))
        assert out["data_quality_precheck"]["notice"] == ""

    def test_the_notice_helper_reads_the_node_output(self):
        node = create_data_quality_check(
            filings_provider=lambda ticker, date: [Q2, Q3]
        )
        state = self._state()
        state.update(node(state))
        assert "Fundamentals are not current" in precheck_notice_from_state(state)
        assert precheck_notice_from_state(self._state()) == ""


class TestGateReusesThePrecheck:
    """The analysis and the gate must be the same computation.

    If the managers are told "Q2 is stale" but the gate recomputes with
    different inputs, a run can be debated as blocked and then approved (or
    the reverse). The gate reuses the pre-check's verdict.
    """

    def test_the_gate_blocks_on_the_precheck_verdict_without_recomputing(self):
        from tradingagents.dataflows.gate_integration import evaluate_decision

        state = {
            "company_of_interest": "BRK-B",
            "trade_date": "2026-11-08",
            "market_report": "", "sentiment_report": "", "news_report": "",
            "fundamentals_report": "Equity: 747910 USD million as of 2026-Q2.",
            "investment_debate_state": {"bull_history": "", "bear_history": "",
                                        "history": "", "current_response": ""},
            "trader_investment_plan": "Entry 556.00, stop 542.50, ATR 9.408.",
            "risk_debate_state": {"aggressive_history": "", "conservative_history": "",
                                  "neutral_history": "", "history": ""},
            "investment_plan": "",
            "final_rating": "Overweight",
            "final_trade_decision": "**Rating**: Overweight",
            "data_quality_precheck": {
                "blocks_execution": True,
                "blocking_codes": ["FUNDAMENTALS_STALE"],
                "notice": "…",
                "freshness": {
                    "status": "STALE_FUNDAMENTALS",
                    "reason_code": "FUNDAMENTALS_STALE",
                    "latest_known_period": "2026-Q3",
                    "latest_known_period_end": "2026-09-30",
                    "used_period": "2026-Q2",
                    "used_period_end": "2026-06-30",
                    "reason": "the report uses an older period",
                },
            },
        }
        # No fundamentals_filings passed: without the state verdict the gate
        # would not check freshness at all. The reuse is what makes it block.
        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08", state, snapshot_id="reuse-1",
            equity=100_000.0, risk_budget=1_000.0, max_symbol_exposure=0.05,
            trigger_met=True, market_open=True,
        )
        assert decision.action.value == "BLOCK"
        verdict = record.execution_verdict.to_dict()
        assert verdict["execution_approved"] is False
        assert verdict["authorized_orders"] == []
        # And the audit carries the reused freshness verdict, not a null.
        freshness = record.to_dict()["data_quality"]["fundamentals_freshness"]
        assert freshness["status"] == "STALE_FUNDAMENTALS"

    """The notice reaches the two managers that conclude the run."""

    def test_research_manager_prompt_carries_the_notice(self):
        from unittest.mock import MagicMock

        from tradingagents.agents.managers.research_manager import (
            create_research_manager,
        )

        captured = {}
        llm = MagicMock()
        # with_structured_output raises so the free-text path runs and the
        # prompt is captured on invoke.
        llm.with_structured_output.side_effect = NotImplementedError
        llm.invoke.side_effect = lambda prompt: (
            captured.__setitem__("prompt", prompt) or MagicMock(content="plan")
        )
        state = {
            "company_of_interest": "BRK-B", "trade_date": "2026-11-08",
            "investment_debate_state": {"bull_history": "b", "bear_history": "s",
                                        "history": "debate", "count": 1,
                                        "current_response": ""},
            "data_quality_precheck": {
                "blocks_execution": True,
                "blocking_codes": ["FUNDAMENTALS_STALE"],
                "notice": "## Deterministic data-quality findings (binding)\n"
                          "- **Fundamentals are not current:** 2026-Q2 vs 2026-Q3",
            },
        }
        create_research_manager(llm)(state)
        assert "Fundamentals are not current" in captured["prompt"]
        assert "2026-Q3" in captured["prompt"]

    def test_portfolio_manager_prompt_carries_the_notice(self):
        from unittest.mock import MagicMock

        from tradingagents.agents.managers.portfolio_manager import (
            create_portfolio_manager,
        )

        captured = {}
        structured = MagicMock()
        structured.invoke.side_effect = lambda prompt: (
            captured.__setitem__("prompt", prompt) or None
        )
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        state = {
            "company_of_interest": "BRK-B", "trade_date": "2026-11-08",
            "risk_debate_state": {"history": "h", "aggressive_history": "",
                                  "conservative_history": "", "neutral_history": "",
                                  "current_aggressive_response": "",
                                  "current_conservative_response": "",
                                  "current_neutral_response": "", "count": 1},
            "investment_plan": "P", "trader_investment_plan": "T",
            "data_quality_precheck": {
                "blocks_execution": True,
                "blocking_codes": ["ARITHMETIC_MISMATCH"],
                "notice": "## Deterministic data-quality findings (binding)\n"
                          "- **Arithmetic does not support the report**",
            },
        }
        with contextlib.suppress(Exception):
            create_portfolio_manager(llm)(state)
        assert "Arithmetic does not support" in captured["prompt"]
