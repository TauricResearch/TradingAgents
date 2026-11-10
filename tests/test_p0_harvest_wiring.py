"""P0.2 wiring: the fact registry populates from the run's own reports.

The claim harvester turns the analysts' labelled metric statements into
AgentFact records, so the cross-agent conflict gate runs without explicit
caller input. Harvested facts are unverified by construction — harvesting
proves what an agent asserted, not that it is true.
"""

from __future__ import annotations

import json

import pytest

from tradingagents.dataflows.claim_harvester import harvest_facts


class TestHarvesting:
    def test_labelled_metrics_are_harvested(self):
        report = (
            "## Fundamentals\n"
            "Stockholders Equity: 747,900 USD million as of 2026-Q2.\n"
            "Total Assets: 1,150,000 USD million.\n"
        )
        facts = harvest_facts({"fundamentals_report": report})
        keys = {f.fact_key for f in facts}
        assert "stockholders_equity" in keys
        assert "total_assets" in keys
        equity = next(f for f in facts if f.fact_key == "stockholders_equity")
        assert equity.value == pytest.approx(747_900.0)
        assert equity.unit == "USD_million"
        assert equity.period == "2026-Q2"
        assert equity.agent == "fundamentals"

    def test_a_buyback_statement_is_scoped_to_its_quarter(self):
        report = "Q3 2026 buyback of approximately $9.6 billion."
        facts = harvest_facts({"news_report": report})
        assert len(facts) == 1
        fact = facts[0]
        assert fact.fact_key == "buyback_amount"
        assert fact.value == pytest.approx(9.6)
        assert fact.unit == "USD_billion"
        assert fact.period == "2026-Q3"
        assert fact.agent == "news"

    def test_bare_numbers_are_never_harvested(self):
        report = "The stock traded between 557 and 562 on Friday."
        assert harvest_facts({"market_report": report}) == []

    def test_unknown_labels_are_skipped(self):
        report = "Moonshot potential: 100 billion stars."
        assert harvest_facts({"sentiment_report": report}) == []

    def test_harvested_facts_are_never_verified(self):
        report = "Revenue: 25,000 USD million in Q3 2026."
        facts = harvest_facts({"fundamentals_report": report})
        assert facts and all(not f.verified for f in facts)

    def test_an_unscoped_statement_has_no_period(self):
        report = "Free Cash Flow: 3,400 USD million."
        facts = harvest_facts({"fundamentals_report": report})
        assert facts and facts[0].period is None

    def test_empty_reports_harvest_nothing(self):
        assert harvest_facts({}) == []
        assert harvest_facts({"news_report": ""}) == []


class TestRegistryWiring:
    def _state(self, **reports):
        state = {
            "company_of_interest": "BRK-B",
            "trade_date": "2026-11-08",
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {"bull_history": "", "bear_history": "",
                                        "history": "", "current_response": ""},
            "trader_investment_plan": "",
            "risk_debate_state": {"aggressive_history": "", "conservative_history": "",
                                  "neutral_history": "", "history": ""},
            "investment_plan": "",
            "final_rating": "Hold",
            "final_trade_decision": "**Rating**: Hold\nMaintain.",
            # A snapshot the engine can certify from, so these tests measure
            # the harvest wiring rather than the authorisation rule (§4: no
            # certified metric means no order).
            "verified_market_snapshot": {"close": 570.89, "sma200": 497.723},
        }
        state.update(reports)
        return state

    def test_agreeing_reports_do_not_block(self):
        from tradingagents.dataflows.gate_integration import evaluate_decision
        from tradingagents.dataflows.math.run_registry import (
            RunInputs,
            build_run_registry,
        )

        state = self._state(
            news_report="Q3 2026 buyback of approximately $9.6 billion.",
            sentiment_report="Q3 2026 buyback of approximately $9.6 billion.",
        )
        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08", state, snapshot_id="s1",
            # §4: a certified metric is required for approval. The subject here
            # is the fact-harvest wiring, so the run is made otherwise sound.
            metric_registry=build_run_registry(
                RunInputs(price=570.89, sma200=497.723)),
        )
        assert record.fact_registry is not None
        assert not record.fact_registry.blocks_decision
        assert "DATA_QUALITY_BLOCKED" not in [r.value for r in decision.reasons]

    def test_conflicting_reports_block_through_the_real_path(self, tmp_path):
        """Two agents asserting incompatible values for the same scoped
        fact: the harvested conflict blocks the decision."""
        from tradingagents.dataflows.gate_integration import (
            evaluate_decision,
            write_audit_record,
        )

        state = self._state(
            news_report="Q3 2026 buyback of approximately $9.6 billion.",
            fundamentals_report="Q3 2026 Share Repurchases: 100 USD million.",
        )
        record, decision = evaluate_decision(
            "BRK-B", "2026-11-08", state, snapshot_id="s1",
        )
        assert record.fact_registry is not None
        assert record.fact_registry.blocks_decision
        assert decision.action.value == "BLOCK"
        assert "DATA_QUALITY_BLOCKED" in [r.value for r in decision.reasons]

        path = write_audit_record(record, str(tmp_path))
        data = json.loads(path.read_text(encoding="utf-8"))
        dq = data["data_quality"]
        assert dq["status"] == "BLOCKED_BY_CLAIMS"
        assert "buyback_amount" in dq["blocking_claims"]
        assert dq["fact_registry"]["conflicts"]

    def test_a_caller_supplied_registry_takes_precedence(self):
        """An explicit registry is used as-is; harvesting does not run."""
        from tradingagents.dataflows.fact_registry import register_facts
        from tradingagents.dataflows.gate_integration import evaluate_decision

        state = self._state(
            news_report="Q3 2026 buyback of approximately $9.6 billion.",
        )
        empty = register_facts([])
        record, _ = evaluate_decision(
            "BRK-B", "2026-11-08", state, snapshot_id="s1",
            fact_registry_report=empty,
        )
        assert record.fact_registry is empty
        assert record.fact_registry.facts == []

    def test_reports_without_metrics_harvest_nothing(self):
        from tradingagents.dataflows.gate_integration import evaluate_decision

        state = self._state(
            news_report="The market awaits the next session.",
        )
        record, _ = evaluate_decision(
            "BRK-B", "2026-11-08", state, snapshot_id="s1",
        )
        assert record.fact_registry is None
