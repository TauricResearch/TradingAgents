"""P1: the metric registry reaches the gate, and the two outcomes stay distinct.

The data lineage audit found F6: `_evaluate_reliability` called
`evaluate_decision` without a `metric_registry`, so the claims validator could
verify nothing, every labelled figure was `NOT_CHECKABLE`, and every run blocked.

The fix has two halves, and both are tested here through the **real code path**
(`TradingAgentsGraph.record_decision` → `_evaluate_reliability` →
`evaluate_decision`), not through the individual functions:

1. **The registry is built and supplied** — per run, from the engine's own
   computations.
2. **Two outcomes are separated** — a report that explains the problem, and an
   order that is refused. Solving F6 by making arithmetic errors non-blocking
   would be the wrong fix; these tests pin that contradictions still block.
"""

from __future__ import annotations

import json

import pytest

from tradingagents.dataflows.execution_gate import ExecutionAction, GateReason
from tradingagents.dataflows.gate_integration import (
    ExecutionAuthorization,
    ReportOutcome,
    attach_registry_status,
    attach_to_state,
    evaluate_decision,
)
from tradingagents.dataflows.math.metric_record import metric
from tradingagents.dataflows.math.registry import MetricRegistry
from tradingagents.dataflows.math.run_registry import (
    RunInputs,
    build_run_registry,
    registry_inputs_from_state,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph

BUDGET = {"equity": 100_000.0, "cash": 100_000.0,
          "risk_budget": 1_000.0, "max_symbol_exposure": 0.05}


def _read_audit(results_root, ticker, analysis_date):
    """The audit of the single run this test made (run-scoped since §2 of P4)."""
    directory = results_root / ticker / "reliability_audit"
    audits = sorted(directory.glob(f"audit_{analysis_date}_*.json"))
    assert len(audits) == 1, f"expected one run-scoped audit, got {audits}"
    return json.loads(audits[0].read_text(encoding="utf-8"))


def _state(market: str = "", plan: str = "Entry 557.00, stop 547.40, ATR 9.408."):
    return {
        "company_of_interest": "BRK-B",
        "trade_date": "2026-11-09",
        "market_report": market,
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {"bull_history": "", "bear_history": "",
                                    "history": "", "current_response": ""},
        "trader_investment_plan": plan,
        "risk_debate_state": {"aggressive_history": "", "conservative_history": "",
                              "neutral_history": "", "history": ""},
        "investment_plan": "",
        "final_rating": "Overweight",
        "final_trade_decision": "**Rating**: Overweight\nBuy.",
    }


def _run(registry, state, **extra):
    """Evaluate through the real entry point and attach both outcomes."""
    record, decision = evaluate_decision(
        "BRK-B", "2026-11-09", state, snapshot_id="t", trigger_met=True,
        metric_registry=registry, **BUDGET, **extra)
    attach_to_state(state, decision)
    attach_registry_status(state, registry)
    return record, decision, state


def _graph(tmp_path) -> TradingAgentsGraph:
    """A graph whose reliability path is real and whose side effects are not."""
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {
        "results_dir": str(tmp_path / "results"),
        "deep_think_llm": "glm-5.3:cloud",
        "quick_think_llm": "deepseek-v4.1-flash:cloud",
        "fundamentals_freshness_gate": False,
        "risk_per_trade_pct": 0.01,
        "max_symbol_exposure": 0.05,
    }
    graph.selected_analysts = []

    class _Log:
        def store_decision(self, **kwargs):
            self.stored = kwargs

    graph.memory_log = _Log()
    return graph


# ===========================================================================
# §5.1-5.4 — the registry reaches the gate
# ===========================================================================
class TestRegistryReachesTheGate:
    def test_a_supplied_registry_is_used_for_verification(self):
        """§5.1: a valid registry is delivered and its metrics are checked."""
        registry = build_run_registry(
            RunInputs(price=576.74, book_value_per_share=359.5599))
        record, decision, state = _run(registry, _state("P/B of 1.6040x."))
        assert state["metric_registry_status"]["metrics_usable"] >= 1
        # The claim was compared, not merely ignored.
        claims = record.math_verdict.report.claims
        assert claims is not None
        assert len(claims.results) >= 1
        assert decision.action is ExecutionAction.PROPOSE_PAPER_ORDER

    def test_the_registry_is_per_run_not_shared(self):
        """§3: two runs get two registries; one cannot certify the other."""
        first = build_run_registry(RunInputs(price=576.74,
                                             book_value_per_share=359.5599),
                                   run_id="run-a")
        second = build_run_registry(RunInputs(), run_id="run-b")
        assert first is not second
        assert first.run_id != second.run_id
        assert len(first.usable) > len(second.usable)
        # Run A certified a P/B; run B recorded the same metric as
        # NOT_COMPUTABLE — present, so the audit shows the attempt, but with no
        # value to certify. The second registry inherits nothing from the first.
        assert first.get("price_to_book").is_usable is True
        assert second.get("price_to_book").is_usable is False
        assert second.value("price_to_book") is None

    def test_the_registry_is_built_from_engine_computation_not_prose(self):
        """§3: values come from `math/`, and a missing input is NOT_COMPUTABLE."""
        registry = build_run_registry(RunInputs(price=576.74,
                                                book_value_per_share=359.5599))
        pb = registry.get("price_to_book")
        assert pb is not None
        assert pb.formula_id == "price_div_bvps"
        assert pb.display == "1.6040"
        # An input the run does not have is recorded as missing, not invented.
        sma = registry.get("distance_from_sma200")
        assert sma is not None
        assert sma.value is None


# ===========================================================================
# §5.2-5.3 — missing and empty registry
# ===========================================================================
class TestMissingOrEmptyRegistry:
    def test_a_missing_registry_blocks_execution(self):
        """§5.2/§5.8: no registry means nothing certified, so no order."""
        _, decision, state = _run(None, _state("P/B of 1.6040x."))
        assert decision.action is ExecutionAction.BLOCK
        assert state["execution_authorization"] == str(
            ExecutionAuthorization.BLOCKED)
        assert "NO_CERTIFIED_METRIC" in state["execution_reason_codes"]

    def test_an_empty_registry_blocks_execution(self):
        """§5.3: present but certifying nothing is the same as absent."""
        empty = build_run_registry(RunInputs())
        _, decision, state = _run(empty, _state())
        assert decision.action is ExecutionAction.BLOCK
        assert state["metric_registry_status"]["is_empty"] is False
        assert state["metric_registry_status"]["metrics_usable"] == 0
        assert state["execution_authorization"] == str(
            ExecutionAuthorization.BLOCKED)

    def test_a_missing_registry_still_produces_a_report(self):
        """§4: the reader gets the diagnosis even when the order is refused."""
        _, _, state = _run(None, _state("P/B of 1.6040x."))
        assert state["report_outcome"] in (
            str(ReportOutcome.COMPLETED),
            str(ReportOutcome.COMPLETED_WITH_WARNINGS))
        assert state["report_outcome"] != str(ReportOutcome.FAILED)


# ===========================================================================
# §5.4-5.5 — valid and invalid metrics
# ===========================================================================
class TestValidAndInvalidMetrics:
    def test_correct_metrics_approve_the_order(self):
        """§5.4: certified values that agree with the report authorise."""
        registry = build_run_registry(
            RunInputs(price=576.74, book_value_per_share=359.5599))
        _, decision, state = _run(registry, _state("P/B of 1.6040x."))
        assert state["execution_authorization"] == str(
            ExecutionAuthorization.APPROVED)
        assert state["report_outcome"] == str(ReportOutcome.COMPLETED)

    def test_a_contradicted_metric_blocks(self):
        """§5.5: 1.35x against a computed 1.6040 is disproved, so it blocks."""
        registry = build_run_registry(
            RunInputs(price=576.74, book_value_per_share=359.5599))
        _, decision, state = _run(registry, _state("P/B of 1.35x."))
        assert decision.action is ExecutionAction.BLOCK
        assert state["execution_authorization"] == str(
            ExecutionAuthorization.BLOCKED)
        codes = [r.value for r in decision.reasons]
        assert "NUMERIC_CLAIM_MISMATCH" in codes

    def test_a_refused_metric_in_the_registry_blocks(self):
        """A registry carrying a refused metric cannot certify the decision."""
        registry = MetricRegistry(run_id="t")
        registry.register(metric("price_to_book", "1.6040",
                                 formula_id="price_div_bvps",
                                 llm_claimed_value="1.35", tolerance="0.02"))
        assert registry.blocks_decision is True
        _, decision, _ = _run(registry, _state())
        assert decision.action is ExecutionAction.BLOCK

    def test_not_computable_is_not_a_contradiction(self):
        """The distinction F6 got wrong: a gap is reported, not a refusal.

        An absent input leaves the metric unusable — so the order is blocked by
        NO_CERTIFIED_METRIC — but it must not be reported as a contradiction,
        which is what made every run fail.
        """
        registry = build_run_registry(RunInputs(price=576.74))
        sma = registry.get("distance_from_sma200")
        assert sma is not None
        assert sma.blocks_decision is False
        assert registry.blocking == []


# ===========================================================================
# §5.6 — the validator is really called
# ===========================================================================
class TestValidatorIsCalled:
    def test_the_claims_validator_produced_results(self):
        """§5.6: proof the validator ran, not just that it exists."""
        registry = build_run_registry(
            RunInputs(price=576.74, book_value_per_share=359.5599))
        record, _, _ = _run(registry, _state("P/B of 1.35x."))
        claims = record.math_verdict.report.claims
        assert claims is not None
        assert claims.results, "the claims validator produced no result"
        assert any(r.verdict.value == "MISMATCH" for r in claims.results)

    def test_the_claim_carries_the_agent_and_both_values(self):
        registry = build_run_registry(
            RunInputs(price=576.74, book_value_per_share=359.5599))
        record, _, _ = _run(registry, _state("P/B of 1.35x."))
        payload = record.math_verdict.report.claims.summary()
        claim = payload["claims"][0]
        assert claim["agent"]
        assert claim["value"] == "1.35"
        assert claim.get("computed_value") == "1.6040"


# ===========================================================================
# §5.7-5.9 — outcomes, blocking, and zero execution on invalid data
# ===========================================================================
class TestTwoOutcomesAreDistinct:
    def test_report_and_authorization_are_separate_fields(self):
        """§4: a completed report does not imply an approved order."""
        _, _, state = _run(None, _state("P/B of 1.6040x."))
        assert "report_outcome" in state
        assert "execution_authorization" in state
        assert state["report_outcome"] != str(ReportOutcome.FAILED)
        assert state["execution_authorization"] == str(
            ExecutionAuthorization.BLOCKED)

    def test_a_wait_is_not_applicable_not_blocked(self):
        """A sound plan that is simply not time to act is not a refusal."""
        registry = build_run_registry(
            RunInputs(price=576.74, book_value_per_share=359.5599))
        state = _state()
        _, decision = evaluate_decision(
            "BRK-B", "2026-11-09", state, snapshot_id="w", trigger_met=False,
            metric_registry=registry, **BUDGET)
        attach_to_state(state, decision)
        attach_registry_status(state, registry)
        assert decision.action is ExecutionAction.WAIT
        assert state["execution_authorization"] == str(
            ExecutionAuthorization.NOT_APPLICABLE)

    def test_no_order_object_survives_a_block(self):
        """§5.9: zero orders created when the data is invalid."""
        from tradingagents.dataflows.execution_gate import ExecutionGate

        registry = build_run_registry(
            RunInputs(price=576.74, book_value_per_share=359.5599))
        _, decision, _ = _run(registry, _state("P/B of 1.35x."))
        gate = ExecutionGate(analysis_as_of="2026-11-09")
        assert decision.creates_order is False
        assert gate.orders() == []


# ===========================================================================
# §5.10 + the run path itself — through the graph
# ===========================================================================
class TestRealGraphPath:
    def test_record_decision_builds_and_supplies_a_registry(self, tmp_path):
        """The F6 fix, exercised through `record_decision`.

        The audit's finding was precisely that this path never supplied a
        registry; here the same call is made and the registry's status lands in
        the audit the run writes.
        """
        graph = _graph(tmp_path)
        state = _state("P/B of 1.6040x.")
        state["verified_market_snapshot"] = {
            "close": 576.74, "sma200": 502.85, "previous_close": 570.89}
        graph.record_decision("BRK-B", "2026-11-09", state)

        audit = _read_audit(tmp_path / "results", "BRK-B", "2026-11-09")
        assert audit["technical_audit"] is not None
        # And the registry status is on the state the caller sees.
        assert "metric_registry_status" in state
        assert state["metric_registry_status"]["metrics_total"] >= 1
        assert "execution_authorization" in state
        assert "report_outcome" in state

    def test_the_graph_blocks_when_the_state_carries_no_metrics(self, tmp_path):
        """No snapshot and no metric fields: nothing certified, so BLOCK."""
        graph = _graph(tmp_path)
        state = _state("P/B of 1.6040x.")
        graph.record_decision("BRK-B", "2026-11-09", state)
        assert state["execution_authorization"] == str(
            ExecutionAuthorization.BLOCKED)
        assert "NO_CERTIFIED_METRIC" in state.get("execution_reason_codes", [])

    def test_no_bypass_exists_between_state_and_gate(self):
        """§5.10: `attach_to_state` cannot approve what the gate refused."""
        from tradingagents.dataflows.execution_gate import GateDecision

        blocked = GateDecision(ExecutionAction.BLOCK,
                               (GateReason.INVALID_PRICE_TO_BOOK,), "BRK-B")
        state: dict = {}
        attach_to_state(state, blocked)
        attach_registry_status(state, None)
        assert state["execution_authorization"] == str(
            ExecutionAuthorization.BLOCKED)


class TestRegistryInputsFromState:
    def test_values_are_read_from_the_snapshot_only(self):
        inputs = registry_inputs_from_state({
            "verified_market_snapshot": {"close": 576.74, "sma50": 557.9},
        })
        assert inputs.price == pytest.approx(576.74)
        assert inputs.sma50 == pytest.approx(557.9)
        # Fields the state does not carry stay absent rather than invented.
        assert inputs.sma200 is None
        assert inputs.eps_ttm is None

    def test_an_absent_snapshot_yields_no_inputs(self):
        inputs = registry_inputs_from_state({})
        assert inputs.price is None
        assert build_run_registry(inputs).usable == []
