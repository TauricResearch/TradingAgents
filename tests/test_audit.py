"""Phase 6 — structured audit trail tests (contract sections 8 and 10).

The audit assembles the earlier phases' typed verdicts into the contract's
schema shape. It never invents values: fields the run did not produce stay
None. The BRK-B weekend case is the end-to-end fixture: OVERWEIGHT opinion,
WAIT action, unobservable reaction — rendered both as JSON and as the
few-second human summary. Pure logic, frozen verdicts, no network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from tests.fixtures.brk_b_2026_11_08 import ATR_14, STOP_LOSS, TRANCHE_3_ENTRY
from tradingagents.dataflows.audit import SCHEMA_VERSION, AuditRecord
from tradingagents.dataflows.causal_guard import (
    NOT_YET_OBSERVABLE,
    evaluate_post_event_pricing,
)
from tradingagents.dataflows.execution_gate import (
    ExecutionAction,
    PlanInput,
    evaluate_plan,
)
from tradingagents.dataflows.fact_checker import (
    Claim,
    ClaimClassification,
    check_claims,
)
from tradingagents.dataflows.portfolio_decision import (
    map_legacy_rating,
    with_execution_action,
)
from tradingagents.dataflows.provenance import ProvenanceRegistry, verified_fact
from tradingagents.dataflows.risk_engine import (
    RiskReason,
    portfolio_risk_check,
    validate_stop,
)


def _registry() -> ProvenanceRegistry:
    reg = ProvenanceRegistry(snapshot_id="snap-brk-1")
    reg.add(verified_fact(
        "q3_earnings", 12705, "USD_million",
        period="2026-Q3", period_end="2026-09-30",
        source_type="company_release", source_uri="https://example.com/q3",
        published_at=datetime(2026, 11, 7, 12, 0, tzinfo=UTC),
        retrieved_at=datetime(2026, 11, 8, 12, 0, tzinfo=UTC),
        snapshot_id="snap-brk-1",
    ))
    return reg


def _brk_b_record() -> AuditRecord:
    """The full BRK-B weekend case, assembled from real phase verdicts."""
    causal = evaluate_post_event_pricing(
        "2026-11-07",
        ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"],
        as_of_date="2026-11-08",
    )
    stop = validate_stop(TRANCHE_3_ENTRY, STOP_LOSS, ATR_14)
    plan = PlanInput(
        ticker="BRK-B", rating="OVERWEIGHT", intent="ACCUMULATE_CONDITIONALLY",
        trigger_met=False, risk_blocked=True,
        risk_reasons=(RiskReason.STOP_BUFFER_TOO_TIGHT,),
        post_event_status=causal.status,
        signal_as_of="2026-11-08", analysis_as_of="2026-11-08",
        market_open=False,
    )
    gate = evaluate_plan(plan)
    strategic = with_execution_action(
        map_legacy_rating("Overweight", "BRK-B", horizon_months=(12, 18)),
        gate.action,
        tuple(r.value for r in gate.reasons),
    )
    fact_check = check_claims(
        [Claim("C-001", "Il mercato ha già assorbito il Q3",
               ClaimClassification.CAUSAL_INFERENCE, blocking=True)],
        _registry(), post_event_status=causal.status,
    )
    return AuditRecord(
        ticker="BRK-B",
        analysis_as_of="2026-11-08",
        snapshot_id="snap-brk-1",
        policy_version="reliability-contract-2026-11",
        model_versions={"deep": "GLM-5.3", "quick": "DeepSeek-V4.1-Flash"},
        provenance=_registry(),
        causal=causal,
        stop_validation=stop,
        portfolio_risk=portfolio_risk_check(None, None),
        gate=gate,
        strategic=strategic,
        fact_check=fact_check,
        session_date="2026-11-06",
        close=570.89,
        currency="USD",
    )


# ---------------------------------------------------------------------------
# Schema shape and no-invention guarantees
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_record_carries_schema_version_and_stable_run_id():
    record = _brk_b_record()
    other = AuditRecord(
        ticker="BRK-B", analysis_as_of="2026-11-08", snapshot_id="snap-brk-1",
        policy_version="x",
    )
    assert record.to_dict()["schema_version"] == SCHEMA_VERSION
    # Same inputs -> same run id: re-auditing is idempotent.
    assert other.run_id == record.run_id
    # A different snapshot is a different run.
    changed = AuditRecord(
        ticker="BRK-B", analysis_as_of="2026-11-08", snapshot_id="snap-other",
        policy_version="x",
    )
    assert changed.run_id != record.run_id


@pytest.mark.unit
def test_brk_b_case_blocks_with_the_contract_reason_codes():
    """The report's plan: invalid stop buffer -> BLOCK, zero orders.

    The gate's verdict is BLOCK (the risk plan fails the ATR buffer, a hard
    condition), carrying also the not-yet reasons — the trigger is unmet,
    the reaction unobservable, the market closed. Either way: no order.
    """
    record = _brk_b_record()
    execution = record.to_dict()["execution"]
    assert execution["action"] == "BLOCK"
    assert execution["market_order_allowed"] is False
    assert execution["paper_order_allowed_now"] is False
    assert "RISK_PLAN_BLOCKED" in execution["reason_codes"]
    assert "ENTRY_TRIGGER_NOT_MET" in execution["reason_codes"]
    assert "POST_EARNINGS_REACTION_UNOBSERVABLE" in execution["reason_codes"]
    assert "MARKET_CLOSED" in execution["reason_codes"]


@pytest.mark.unit
def test_trigger_unmet_without_risk_failure_waits():
    """The pure WAIT shape: valid plan, trigger simply not met yet."""
    causal = evaluate_post_event_pricing(
        "2026-11-07",
        ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"],
        as_of_date="2026-11-08",
    )
    plan = PlanInput(
        ticker="BRK-B", rating="OVERWEIGHT", intent="ACCUMULATE_CONDITIONALLY",
        trigger_met=False, risk_blocked=False,
        post_event_status=causal.status,
        signal_as_of="2026-11-08", analysis_as_of="2026-11-08",
        market_open=False,
    )
    gate = evaluate_plan(plan)
    assert gate.action is ExecutionAction.WAIT
    record = AuditRecord(
        ticker="BRK-B", analysis_as_of="2026-11-08", snapshot_id="snap-brk-1",
        policy_version="p", causal=causal, gate=gate,
    )
    execution = record.to_dict()["execution"]
    assert execution["action"] == "WAIT"
    assert "ENTRY_TRIGGER_NOT_MET" in execution["reason_codes"]
    assert "POST_EARNINGS_REACTION_UNOBSERVABLE" in execution["reason_codes"]


@pytest.mark.unit
def test_strategy_and_execution_stay_separate_in_the_record():
    """OVERWEIGHT opinion coexists with a non-executing action in one record."""
    data = _brk_b_record().to_dict()
    assert data["strategy"]["rating"] == "OVERWEIGHT"
    assert data["strategy"]["legacy_label"] == "Overweight"
    assert data["strategy"]["horizon_months"] == [12, 18]
    assert data["execution"]["action"] in ("WAIT", "BLOCK")
    assert data["execution"]["paper_order_allowed_now"] is False


@pytest.mark.unit
def test_event_record_carries_the_causal_verdict():
    event = _brk_b_record().to_dict()["events"][0]
    assert event["publication_date"] == "2026-11-07"
    assert event["last_session_before"] == "2026-11-06"
    assert event["post_event_price_status"] == NOT_YET_OBSERVABLE


@pytest.mark.unit
def test_risk_record_shows_the_unvalidated_stop():
    """The 543.70/543.50 plan: stop UNVALIDATED, no quantity proposed."""
    risk = _brk_b_record().to_dict()["risk"]
    assert risk["stop_model"] == "UNVALIDATED"
    assert risk["stop_atr_multiple"] == pytest.approx(0.20 / 9.408, abs=1e-6)
    assert risk["qty_proposed"] is None
    assert risk["max_portfolio_loss_fraction"] is None  # no equity: never invented
    assert risk["gap_stress_test_passed"] is False


@pytest.mark.unit
def test_data_quality_carries_the_blocking_claim():
    dq = _brk_b_record().to_dict()["data_quality"]
    assert dq["status"] == "BLOCKED_BY_CLAIMS"
    assert dq["blocking_claims"] == ["C-001"]
    assert dq["fact_check_summary"]["refuted"] == 1


@pytest.mark.unit
def test_audit_section_carries_versions_without_secrets():
    audit = _brk_b_record().to_dict()["audit"]
    assert audit["snapshot_id"] == "snap-brk-1"
    assert audit["model_versions"] == {"deep": "GLM-5.3", "quick": "DeepSeek-V4.1-Flash"}
    # No key material anywhere in the record.
    text = json.dumps(_brk_b_record().to_dict())
    for secret in ("api_key", "API_KEY", "token", "password", "secret"):
        assert secret.lower() not in text.lower()


@pytest.mark.unit
def test_json_output_is_parseable_and_complete():
    data = json.loads(_brk_b_record().to_json())
    for section in ("schema_version", "run_id", "ticker", "analysis_as_of",
                    "market_snapshot", "events", "strategy", "execution",
                    "risk", "data_quality", "audit"):
        assert section in data


@pytest.mark.unit
def test_absent_phases_stay_none_not_invented():
    """A record with no verdicts reports None, never fabricated values."""
    bare = AuditRecord(
        ticker="X", analysis_as_of="2026-11-08", snapshot_id="s",
        policy_version="p",
    )
    data = bare.to_dict()
    assert data["events"][0]["post_event_price_status"] is None
    assert data["strategy"]["rating"] is None
    assert data["execution"]["action"] is None
    assert data["risk"]["stop_model"] == "UNVALIDATED"
    assert data["risk"]["qty_proposed"] is None
    assert data["data_quality"]["status"] is None


# ---------------------------------------------------------------------------
# The few-second human read (contract §10)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_human_summary_separates_opinion_from_action():
    text = _brk_b_record().render_human_summary()
    assert "Opinion: OVERWEIGHT (ACCUMULATE_CONDITIONALLY) [legacy: Overweight]" in text
    assert "Execution: BLOCK" in text
    assert "RISK_PLAN_BLOCKED" in text
    assert "BLOCKED by refuted claims: C-001" in text
    assert "Orders: none" in text


@pytest.mark.unit
def test_human_summary_without_verdicts_is_honest():
    bare = AuditRecord(ticker="X", analysis_as_of="2026-11-08",
                       snapshot_id="s", policy_version="p")
    text = bare.render_human_summary()
    assert "Execution: NOT EVALUATED" in text
    assert "Orders: none" in text
