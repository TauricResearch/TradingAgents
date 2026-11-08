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
    GateDecision,
    PlanInput,
    evaluate_plan,
)
from tradingagents.dataflows.filing_freshness import (
    check_filing_freshness,
)
from tradingagents.dataflows.plan_extraction import extract_plan_numbers
from tradingagents.dataflows.portfolio_decision import (
    map_legacy_rating,
    with_execution_action,
)
from tradingagents.dataflows.risk_engine import (
    DEFAULT_MIN_ENTRY_STOP_ATR,
    RiskReason,
    StopValidation,
    size_with_exposure_cap,
    validate_stop_side,
)

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
    # P0 data-quality inputs (all optional; absent checks are not guessed).
    fundamentals_filings: list | None = None,
    used_fundamentals_period_end: str | None = None,
    used_fundamentals_period: str | None = None,
    fact_registry_report=None,
    position_direction: str | None = None,
    # P0.5 sizing inputs (optional; absent portfolio context never invents
    # a size — the sizing is skipped rather than guessed).
    equity: float | None = None,
    cash: float | None = None,
    risk_budget: float | None = None,
    max_symbol_exposure: float | None = None,
) -> tuple[AuditRecord, GateDecision]:
    """Evaluate a finished run's decision through the gate and audit it.

    The plan's numbers (``entry``/``stop``/``atr``) come from the decision's
    own text when its caller extracted them; when absent the risk check is
    skipped rather than guessed, and the gate sees a valid plan with no
    trigger — the honest default. Returns ``(audit_record, gate_decision)``.

    P0 data-quality gates, all fail-closed:

    - ``fundamentals_filings`` + ``used_fundamentals_period_end``: the
      freshness gate compares the period the analyst used against the
      latest filing known at the analysis date; a stale or undatable
      period blocks (``FUNDAMENTALS_STALE`` / ``FUNDAMENTALS_UNAVAILABLE``).
    - ``fact_registry_report``: an unresolved cross-agent conflict over a
      material fact blocks (``DATA_QUALITY_BLOCKED``).
    - ``position_direction``: the stop must sit on the protective side for
      the position's direction; a wrong-side stop blocks. Defaults to the
      plan text's own direction when not supplied.
    - ``equity``/``cash``/``risk_budget``/``max_symbol_exposure``: with the
      plan's numbers (extracted from the decision text when not passed),
      sizing runs under BOTH the stop-distance budget and the per-symbol
      exposure cap; without portfolio context no size is invented.
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

    # Risk engine: the plan's numbers come from the caller when supplied,
    # else from the run's own trader plan text (labelled patterns only —
    # bare numbers in prose are never guessed).
    plan_numbers = extract_plan_numbers(
        final_state.get("trader_investment_plan")
    )
    eff_entry = entry if entry is not None else plan_numbers.entry
    eff_stop = stop if stop is not None else plan_numbers.stop
    eff_atr = atr if atr is not None else plan_numbers.atr
    eff_direction = position_direction or plan_numbers.direction

    stop_validation = None
    risk_blocked = False
    risk_reasons = ()
    sizing = None
    if eff_entry is not None and eff_stop is not None and eff_atr is not None:
        # The ATR-buffer check uses the absolute distance so a SHORT plan's
        # stop above the entry is measured by the same rule; the side check
        # below (validate_stop_side) enforces the direction itself.
        distance = abs(eff_entry - eff_stop)
        if distance <= 0:
            risk_blocked = True
            risk_reasons = ("INVALID_STOP",)
        else:
            atr_multiple = distance / eff_atr
            if atr_multiple < DEFAULT_MIN_ENTRY_STOP_ATR:
                stop_validation = StopValidation(
                    False, eff_entry, eff_stop, eff_atr, distance,
                    atr_multiple, DEFAULT_MIN_ENTRY_STOP_ATR,
                    RiskReason.STOP_BUFFER_TOO_TIGHT)
                risk_blocked = True
                risk_reasons = (RiskReason.STOP_BUFFER_TOO_TIGHT,)
            else:
                stop_validation = StopValidation(
                    True, eff_entry, eff_stop, eff_atr, distance,
                    atr_multiple, DEFAULT_MIN_ENTRY_STOP_ATR, RiskReason.OK)

            # P0.5: size under BOTH the stop-distance budget and the
            # per-symbol exposure cap. Without portfolio context (no
            # equity) no size is invented — the sizing result records
            # PORTFOLIO_CONTEXT_MISSING and the plan cannot pass as
            # executable.
            if not risk_blocked and risk_budget is not None:
                sizing = size_with_exposure_cap(
                    entry=eff_entry, stop=eff_stop, atr=eff_atr,
                    risk_budget=risk_budget, equity=equity,
                    max_symbol_exposure=max_symbol_exposure,
                    direction=eff_direction, cash=cash,
                )
                if sizing.reasons:
                    risk_blocked = True
                    risk_reasons = risk_reasons + sizing.reasons

    # P0: the stop must sit on the protective side for the position's
    # direction. A wrong-side stop protects nothing and blocks the plan.
    stop_side = None
    if eff_entry is not None and eff_stop is not None:
        stop_side = validate_stop_side(eff_entry, eff_stop, eff_direction)
        if stop_side.has_errors:
            risk_blocked = True
            risk_reasons = risk_reasons + ("STOP_WRONG_SIDE",)

    # P0.1: the fundamentals the analyst used must be the freshest
    # authoritative filing known at the analysis date. Stale or undatable
    # fundamentals block — an older quarter must not pass as current.
    freshness = None
    data_quality_blocked = False
    if fundamentals_filings is not None:
        freshness = check_filing_freshness(
            used_fundamentals_period_end, fundamentals_filings, trade_date,
            used_period=used_fundamentals_period,
        )
        if freshness.blocks_decision:
            data_quality_blocked = True

    # P0.2: an unresolved cross-agent conflict over a material fact must
    # not feed an approval.
    if fact_registry_report is not None and fact_registry_report.blocks_decision:
        data_quality_blocked = True

    plan = PlanInput(
        ticker=ticker,
        rating=strategic.rating if strategic else "UNKNOWN",
        intent=strategic.intent if strategic else "MONITOR",
        trigger_met=trigger_met,
        risk_blocked=risk_blocked,
        risk_reasons=risk_reasons,
        data_quality_blocked=data_quality_blocked,
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
    if freshness is not None:
        record.fundamentals_freshness = freshness
    if fact_registry_report is not None:
        record.fact_registry = fact_registry_report
    if sizing is not None:
        record.exposure_sizing = sizing
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
