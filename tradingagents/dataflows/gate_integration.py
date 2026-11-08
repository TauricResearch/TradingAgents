"""End-of-run reliability evaluation: the Execution Gate over the decision.

Wires the Phase 1-6 modules into the live flow's finalization: after the
graph produces its decision, the run's verdicts are assembled into an
:class:`AuditRecord` and the decision is evaluated by the Execution Gate.
The audit JSON is written beside the state log; the gate's action is
attached to the state (``execution_action``) so callers and the CLI can see
whether the decision is an opinion, a plan, or nothing at all.

The gate never blocks *reporting*: the human-readable decision is still
produced and logged exactly as before. What it controls is the execution
vocabulary — a decision whose plan fails the risk engine, or whose causal
claims are refuted, is recorded as WAIT/BLOCK with reason codes rather than
as an executable proposal. No order path exists to begin with; this module
adds the verdict that would govern one.
"""

from __future__ import annotations

import logging
from pathlib import Path

from tradingagents.dataflows.audit import AuditRecord
from tradingagents.dataflows.causal_guard import evaluate_post_event_pricing
from tradingagents.dataflows.execution_gate import (
    ExecutionAction,
    GateDecision,
    PlanInput,
    evaluate_plan,
)
from tradingagents.dataflows.portfolio_decision import (
    map_legacy_rating,
    with_execution_action,
)
from tradingagents.dataflows.risk_engine import validate_stop

logger = logging.getLogger(__name__)

# The state keys the audit reads; all optional, all defaulted.
_POLICY_VERSION = "reliability-contract-2026-11"


def evaluate_decision(
    ticker: str,
    trade_date: str,
    final_state: dict,
    *,
    snapshot_id: str,
    model_versions: dict | None = None,
    sessions: list[str] | None = None,
    event_publication_date: str | None = None,
    entry: float | None = None,
    stop: float | None = None,
    atr: float | None = None,
    trigger_met: bool = False,
    market_open: bool = True,
) -> tuple[AuditRecord, GateDecision]:
    """Evaluate a finished run's decision through the gate and audit it.

    The plan's numbers (``entry``/``stop``/``atr``) come from the decision's
    own text when its caller extracted them; when absent the risk check is
    skipped rather than guessed, and the gate sees a valid plan with no
    trigger — the honest default. Returns ``(audit_record, gate_decision)``.
    """
    rating_label = final_state.get("final_rating") or ""
    # An unreadable rating maps to nothing: the gate sees an unknown
    # vocabulary and blocks, rather than the audit inventing a call (#1170).
    try:
        strategic = map_legacy_rating(rating_label, ticker) if rating_label else None
    except ValueError:
        strategic = None
        logger.warning("Unreadable rating for %s on %s; gate will block",
                       ticker, trade_date)

    # Causal guard: only when the run knows an event and a calendar.
    causal = None
    if event_publication_date and sessions:
        causal = evaluate_post_event_pricing(
            event_publication_date, sessions, as_of_date=trade_date
        )

    # Risk engine: only when the plan's numbers are all present.
    stop_validation = None
    risk_blocked = False
    risk_reasons = ()
    if entry is not None and stop is not None and atr is not None:
        stop_validation = validate_stop(entry, stop, atr)
        risk_blocked = stop_validation.blocked
        risk_reasons = (stop_validation.reason,) if stop_validation.blocked else ()

    plan = PlanInput(
        ticker=ticker,
        rating=strategic.rating if strategic else "UNKNOWN",
        intent=strategic.intent if strategic else "MONITOR",
        trigger_met=trigger_met,
        risk_blocked=risk_blocked,
        risk_reasons=risk_reasons,
        post_event_status=causal.status if causal else None,
        signal_as_of=trade_date,
        analysis_as_of=trade_date,
        market_open=market_open,
    )
    decision = evaluate_plan(plan)

    if strategic:
        strategic = with_execution_action(
            strategic, decision.action,
            tuple(r.value for r in decision.reasons),
        )

    record = AuditRecord(
        ticker=ticker,
        analysis_as_of=trade_date,
        snapshot_id=snapshot_id,
        policy_version=_POLICY_VERSION,
        model_versions=model_versions or {},
        causal=causal,
        stop_validation=stop_validation,
        gate=decision,
        strategic=strategic,
        session_date=sessions[-1] if sessions else None,
    )
    return record, decision


def write_audit_record(record: AuditRecord, results_dir: str) -> Path:
    """Write the audit JSON beside the run's state log, same layout."""
    safe = record.ticker.replace("/", "-")
    directory = Path(results_dir) / safe / "reliability_audit"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"audit_{record.analysis_as_of}.json"
    path.write_text(record.to_json(), encoding="utf-8")
    return path


def attach_to_state(final_state: dict, decision: GateDecision) -> None:
    """Attach the gate's verdict to the run state for callers and the CLI."""
    final_state["execution_action"] = decision.action.value
    final_state["execution_reason_codes"] = [r.value for r in decision.reasons]
