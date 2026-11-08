"""Structured audit trail and machine-readable decision report (Phase 6,
contract sections 8 and 10).

Every run produces, alongside the human report, a structured record that
answers: what was decided, on what data, by which models, through which
checks — and why the outcome was WAIT/BLOCK rather than an order. No
secrets: the audit carries model/provider names and config keys, never
keys themselves.

The record assembles the typed verdicts of the earlier phases (provenance,
causal guard, validator, risk engine, execution gate, fact checker) into
the contract's schema shape. It never invents values: a field the run did
not produce stays ``None``, and the schema version marks which shape the
consumer is reading.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from tradingagents.dataflows.causal_guard import CausalVerdict
from tradingagents.dataflows.execution_gate import ExecutionAction, GateDecision
from tradingagents.dataflows.fact_checker import FactCheckReport
from tradingagents.dataflows.portfolio_decision import StrategicDecision
from tradingagents.dataflows.provenance import ProvenanceRegistry
from tradingagents.dataflows.risk_engine import PortfolioRisk, SizingResult, StopValidation

SCHEMA_VERSION = "1.0"


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class AuditRecord:
    """The run's structured audit: assembled from phase verdicts, JSON-ready.

    ``run_id`` is derived deterministically from the ticker, analysis date
    and snapshot id, so the same analysis re-audited under the same inputs
    carries the same id; ``generated_at`` records when the audit itself was
    written, which is a different moment from ``analysis_as_of``.
    """

    ticker: str
    analysis_as_of: str                       # YYYY-MM-DD
    snapshot_id: str
    policy_version: str
    model_versions: dict = field(default_factory=dict)

    # Phase verdicts (None when the phase did not run for this analysis).
    provenance: ProvenanceRegistry | None = None
    causal: CausalVerdict | None = None
    stop_validation: StopValidation | None = None
    sizing: SizingResult | None = None
    portfolio_risk: PortfolioRisk | None = None
    gate: GateDecision | None = None
    strategic: StrategicDecision | None = None
    fact_check: FactCheckReport | None = None
    # P0 data-quality verdicts (None when the check did not run).
    fundamentals_freshness: object | None = None
    fact_registry: object | None = None

    # Market snapshot as validated (None fields stay None: never invented).
    session_date: str | None = None
    close: float | None = None
    currency: str | None = None

    def __post_init__(self):
        if not self.run_id:
            payload = json.dumps(
                [self.ticker, self.analysis_as_of, self.snapshot_id],
                sort_keys=True,
            )
            self.run_id = hashlib.sha256(payload.encode()).hexdigest()[:16]
        self.generated_at = _utc_now_iso()

    run_id: str = ""

    def to_dict(self) -> dict:
        """The contract's section-8 shape, filled from real verdicts only."""
        gate = self.gate
        strategic = self.strategic
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "ticker": self.ticker,
            "analysis_as_of": self.analysis_as_of,
            "market_snapshot": {
                "session_date": self.session_date,
                "calendar": "XNYS",
                "close": self.close,
                "currency": self.currency,
            },
            "events": [self._event_entry()],
            "strategy": {
                "rating": strategic.rating if strategic else None,
                "intent": strategic.intent if strategic else None,
                "legacy_label": strategic.legacy_label if strategic else None,
                "horizon_months": list(strategic.horizon_months)
                if strategic and strategic.horizon_months else None,
            },
            "execution": self._execution_entry(),
            "risk": self._risk_entry(),
            "data_quality": self._data_quality_entry(),
            "audit": {
                "snapshot_id": self.snapshot_id,
                "policy_version": self.policy_version,
                "model_versions": dict(self.model_versions),
                "run_id": self.run_id,
            },
        }

    def _event_entry(self) -> dict:
        """The causal guard's verdict as the event record; absent stays null."""
        if self.causal is None:
            return {
                "type": "unspecified",
                "publication_date": None,
                "post_event_price_status": None,
            }
        return {
            "type": "material_event",
            "publication_date": self.causal.event_date,
            "last_session_before": self.causal.last_session_before,
            "first_session_after": self.causal.first_session_after,
            "post_event_price_status": self.causal.status,
        }

    def _execution_entry(self) -> dict:
        gate = self.gate
        action = gate.action.value if gate else None
        reasons = [r.value for r in gate.reasons] if gate else []
        return {
            "action": action,
            "market_order_allowed": False,  # paper-only, by construction
            "paper_order_allowed_now": bool(
                gate and gate.action is ExecutionAction.PROPOSE_PAPER_ORDER
            ),
            "entry_triggers_satisfied": bool(
                gate and gate.action is ExecutionAction.PROPOSE_PAPER_ORDER
            ),
            "reason_codes": reasons,
        }

    def _risk_entry(self) -> dict:
        stop = self.stop_validation
        sizing = self.sizing
        portfolio = self.portfolio_risk
        return {
            "stop_model": "VALIDATED" if (stop and not stop.blocked) else "UNVALIDATED",
            "stop_atr_multiple": stop.atr_multiple if stop else None,
            "min_entry_stop_atr": stop.min_atr if stop else None,
            "qty_proposed": sizing.qty if sizing else None,
            "planned_risk": sizing.planned_risk if sizing else None,
            "max_portfolio_loss_fraction": (
                portfolio.max_portfolio_loss_fraction if portfolio else None
            ),
            "planned_risk_pct_equity": (
                portfolio.planned_risk_pct_equity if portfolio else None
            ),
            "gap_stress_test_passed": bool(sizing and sizing.qty > 0),
        }

    def _data_quality_entry(self) -> dict:
        prov = self.provenance
        fc = self.fact_check
        freshness = self.fundamentals_freshness
        registry = self.fact_registry
        if prov is None and fc is None and freshness is None and registry is None:
            return {"status": None, "blocking_claims": []}
        blocking = fc.blocking_claim_ids if fc else []
        freshness_codes = (
            [freshness.reason_code] if freshness is not None
            and freshness.blocks_decision else []
        )
        registry_unresolved = (
            [c.fact_key for c in registry.unresolved_conflicts]
            if registry is not None else []
        )
        if blocking or freshness_codes or registry_unresolved:
            status = "BLOCKED_BY_CLAIMS"
        elif prov and prov.blocking_fact_ids():
            status = "REQUIRES_RECONCILIATION"
        else:
            status = "OK"
        return {
            "status": status,
            "provenance_summary": prov.summary() if prov else None,
            "fact_check_summary": fc.summary() if fc else None,
            "fundamentals_freshness": (
                freshness.summary() if freshness is not None else None
            ),
            "fact_registry": registry.summary() if registry is not None else None,
            "blocking_claims": list(blocking) + freshness_codes + registry_unresolved,
        }

    def to_json(self, *, indent: int = 2) -> str:
        """The audit as JSON, ready to sit beside the human report."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def render_human_summary(self) -> str:
        """The few-second read: opinion, plan, or order? (contract §10)."""
        gate = self.gate
        strategic = self.strategic
        lines = []
        if strategic:
            lines.append(
                f"Opinion: {strategic.rating} ({strategic.intent})"
                + (f" [legacy: {strategic.legacy_label}]" if strategic.legacy_label else "")
            )
        action = gate.action.value if gate else "NOT EVALUATED"
        lines.append(f"Execution: {action}")
        if gate and gate.reasons and gate.reasons != ("OK",):
            lines.append("Reasons: " + ", ".join(r.value for r in gate.reasons))
        if self.fact_check and self.fact_check.blocks_decision:
            lines.append(
                "Data quality: BLOCKED by refuted claims: "
                + ", ".join(self.fact_check.blocking_claim_ids)
            )
        lines.append("Orders: none unless the execution action says otherwise.")
        return "\n".join(lines)
