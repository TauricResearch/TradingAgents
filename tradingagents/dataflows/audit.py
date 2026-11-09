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
    # P0.5 exposure-capped sizing (None when the plan had no numbers or no
    # risk budget — the sizing is skipped, never guessed).
    exposure_sizing: object | None = None
    # P0-D structured execution verdict: the machine-readable answer to
    # "may the desk act now, and if not, exactly why".
    execution_verdict: object | None = None
    # P0-B arithmetic verdicts (None when no snapshot was supplied).
    arithmetic_verdicts: list | None = None
    # Financial Math Engine verdict (§9, §11): the consistency report, the
    # gate reasons the arithmetic produced, and every metric with its
    # formula and operands. Serialized under ``financial_math``.
    math_verdict: object | None = None
    # §9: the session assessment of the price bar this run used, so the
    # technical audit can state whether the decision rested on a confirmed
    # close or on a bar still forming.
    price_snapshot_bar: object | None = None

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
            "financial_math": (
                self.math_verdict.summary() if self.math_verdict is not None else None
            ),
            "audit": {
                "snapshot_id": self.snapshot_id,
                "policy_version": self.policy_version,
                "model_versions": dict(self.model_versions),
                "run_id": self.run_id,
            },
            # §9: a section generated by code, separate from any agent's text,
            # so a reader can see which validations actually ran. A metric is
            # never reported as certified merely because the agents agreed on
            # its value.
            "technical_audit": self._technical_audit_entry(),
        }

    def _technical_audit_entry(self) -> dict:
        """The code-generated audit section (§9).

        Every field is derived from a verdict this run actually produced, never
        from prose. A missing verdict stays ``None``, which is the honest
        answer: an unattempted check is not a pass.
        """
        math = self.math_verdict
        consistency = math.report if math is not None else None
        findings = consistency.findings if consistency is not None else []
        claims = consistency.claims if consistency is not None else None
        freshness = self.fundamentals_freshness
        bar = None
        if self.price_snapshot_bar is not None:
            bar = self.price_snapshot_bar

        return {
            "run_id": self.run_id,
            "analysis_as_of": self.analysis_as_of,
            "last_confirmed_eod_bar": (
                bar.get("last_completed_session") if isinstance(bar, dict) else None
            ),
            "intraday_bar_status": (
                bar.get("market_session_status") if isinstance(bar, dict) else None
            ),
            "bar_is_final": (
                bar.get("is_final") if isinstance(bar, dict) else None
            ),
            "fundamentals_period_used": (
                freshness.used_period_end if freshness is not None else None
            ),
            "fundamentals_reconciliation": (
                freshness.status if freshness is not None else None
            ),
            "math_findings_count": len(findings),
            "math_blocking_codes": list(math.reasons) if math is not None else [],
            "invalidated_metrics": (
                [r.metric for r in self.math_verdict.report.metrics
                 if r.blocks_decision]
                if math is not None else []
            ),
            "numeric_claims_checked": (
                len(claims.results) if claims is not None else 0
            ),
            "numeric_claims_blocking": (
                list(claims.blocking_labels) if claims is not None else []
            ),
            "risk_verdict": {
                "stop_model": (
                    "VALIDATED"
                    if self.stop_validation and not self.stop_validation.blocked
                    else ("UNVALIDATED" if self.stop_validation else None)
                ),
                "qty_proposed": self.sizing.qty if self.sizing else None,
                "planned_risk": self.sizing.planned_risk if self.sizing else None,
                "exposure_capped_qty": (
                    self.exposure_sizing.qty if self.exposure_sizing else None
                ),
            },
            "execution_action": self.gate.action.value if self.gate else None,
            "authorized_orders": (
                list(self.execution_verdict.authorized_orders)
                if self.execution_verdict is not None else []
            ),
            "blocking_reasons": (
                [r.value for r in self.gate.reasons] if self.gate else []
            ),
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
        entry = {
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
        # P0-D: the structured verdict, alongside the gate's raw action.
        verdict = self.execution_verdict
        if verdict is not None:
            entry["verdict"] = verdict.to_dict()
        return entry

    def _risk_entry(self) -> dict:
        stop = self.stop_validation
        sizing = self.sizing
        portfolio = self.portfolio_risk
        exposure = self.exposure_sizing
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
            # P0.5 exposure-capped sizing: which limit bound the size.
            "exposure_capped_qty": exposure.qty if exposure else None,
            "exposure_capped_notional": exposure.notional if exposure else None,
            "exposure_binding_constraint": (
                exposure.binding_constraint if exposure else None
            ),
            "exposure_cap_applied": (
                exposure.exposure_cap_applied if exposure else None
            ),
        }

    def _data_quality_entry(self) -> dict:
        prov = self.provenance
        fc = self.fact_check
        freshness = self.fundamentals_freshness
        registry = self.fact_registry
        arithmetic = self.arithmetic_verdicts or []
        if (prov is None and fc is None and freshness is None
                and registry is None and not arithmetic):
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
        arithmetic = self.arithmetic_verdicts or []
        arithmetic_blocking = [
            v.reason_code for v in arithmetic if v.blocks_decision
        ]
        if arithmetic_blocking:
            status = "BLOCKED_BY_CLAIMS"
        return {
            "status": status,
            "provenance_summary": prov.summary() if prov else None,
            "fact_check_summary": fc.summary() if fc else None,
            "fundamentals_freshness": (
                freshness.summary() if freshness is not None else None
            ),
            "fact_registry": registry.summary() if registry is not None else None,
            "arithmetic": (
                [v.summary() for v in arithmetic] if arithmetic else None
            ),
            "blocking_claims": (
                list(blocking) + freshness_codes + registry_unresolved
                + arithmetic_blocking
            ),
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
