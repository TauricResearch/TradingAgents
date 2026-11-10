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
from enum import StrEnum
from pathlib import Path
from typing import Any

from tradingagents.dataflows.arithmetic import (
    check_price_timestamp_alignment,
    check_stated_percentage,
)
from tradingagents.dataflows.audit import AuditRecord
from tradingagents.dataflows.causal_guard import evaluate_post_event_pricing
from tradingagents.dataflows.claim_harvester import harvest_facts
from tradingagents.dataflows.execution_gate import (
    ExecutionAction,
    GateDecision,
    GateReason,
    PlanInput,
    evaluate_plan,
)
from tradingagents.dataflows.execution_verdict import verdict_from_gate
from tradingagents.dataflows.fact_registry import register_facts
from tradingagents.dataflows.filing_freshness import (
    check_filing_freshness,
)
from tradingagents.dataflows.math.math_gate import evaluate_math
from tradingagents.dataflows.math.report_validation import validate_analyst_report
from tradingagents.dataflows.plan_extraction import extract_plan_numbers
from tradingagents.dataflows.portfolio_decision import (
    map_legacy_rating,
    with_execution_action,
)
from tradingagents.dataflows.risk_engine import (
    DEFAULT_MIN_ENTRY_STOP_ATR,
    RiskReason,
    SizingResult,
    StopValidation,
    size_with_exposure_cap,
    validate_stop_side,
)

logger = logging.getLogger(__name__)

# The state keys the audit reads; all optional, all defaulted.
_POLICY_VERSION = "reliability-contract-2026-11"


def _assess_price_bar(price_snapshot: dict, trade_date: str) -> dict | None:
    """Assess the price bar the run used, for the technical audit (§9).

    Returns ``None`` when the snapshot carries no timestamp: a bar without a
    time cannot be judged, and a null in the audit says so more honestly than an
    invented verdict.
    """
    stamp = price_snapshot.get("price_as_of")
    if not stamp:
        return None
    try:
        from tradingagents.dataflows.math.session import assess_bar

        return assess_bar(stamp, analysis_time=trade_date).summary()
    except Exception:  # noqa: BLE001 — an unparseable stamp yields no verdict
        logger.debug("Could not assess the price bar %r", stamp, exc_info=True)
        return None


def _bar_still_forming(price_snapshot: dict | None,
                       trade_date: str) -> bool:
    """Whether the price bar this run used belongs to a session still trading.

    Reads the snapshot's ``price_as_of`` timestamp, which is when the price was
    observed. A timestamp inside the session means the price is moving, so a
    post-event reaction computed from it is intraday, not settled.

    No timestamp yields ``False``: the causal guard already treats an unknown
    event time as ``INSUFFICIENT_DATA``, and inventing a session state here
    would be a second guess on top of the first.
    """
    if not isinstance(price_snapshot, dict):
        return False
    stamp = price_snapshot.get("price_as_of")
    if not stamp:
        return False
    try:
        from tradingagents.dataflows.math.session import (
            SessionStatus,
            market_session_status,
        )

        return market_session_status(stamp) is SessionStatus.OPEN
    except Exception:  # noqa: BLE001 — an unparseable stamp is not "open"
        return False


def _freshness_from_precheck(precheck: dict):
    """Rebuild a freshness verdict from the graph pre-check's summary.

    The pre-check stores its verdict as a dict; the audit wants the typed
    object. Only the fields the audit reads are restored — this is a
    presentation of the same computation, never a new one.
    """
    data = (precheck or {}).get("freshness") or {}
    if not data:
        return None
    from tradingagents.dataflows.filing_freshness import FreshnessVerdict

    return FreshnessVerdict(
        status=data.get("status", ""),
        reason_code=data.get("reason_code", ""),
        latest_known_period=data.get("latest_known_period"),
        latest_known_period_end=data.get("latest_known_period_end"),
        used_period=data.get("used_period"),
        used_period_end=data.get("used_period_end"),
        reason=data.get("reason", ""),
    )


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
    # P0-B arithmetic inputs: the dated price snapshot the run used, so a
    # percentage the report states can be checked against the data.
    price_snapshot: dict | None = None,
    stated_percentages: dict | None = None,
    # Financial Math Engine (§9, §11): the run's metric registry (verified and
    # refused metrics), and the ATR multiple the report claims for its stop so
    # the arithmetic can be checked against entry/stop/ATR.
    metric_registry=None,
    stated_atr_distance: float | None = None,
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
    - ``price_snapshot`` + ``stated_percentages``: every percentage the
      report states is recomputed from the snapshot; a critical mismatch
      (``ARITHMETIC_MISMATCH``) blocks. A price and an indicator from
      different sessions block too (``PRICE_TIMESTAMP_MISMATCH``).
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

    # Causal guard: only when the run knows an event and a calendar. The
    # session status decides whether a post-event move is a settled reaction or
    # one still forming (§5) — derived from the price bar when one was
    # supplied, so an intraday analysis cannot be mistaken for an EOD one.
    causal = None
    if event_publication_date and sessions:
        bar_open = _bar_still_forming(price_snapshot, trade_date)
        causal = evaluate_post_event_pricing(
            event_publication_date, sessions, as_of_date=trade_date,
            session_still_open=bar_open,
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
            #
            # The size is attempted whenever the plan HAS numbers, even
            # with no budget and no equity: skipping the call is what let a
            # missing budget hide behind an unrelated reason (audit F4 —
            # `qty_proposed`, `planned_risk` and the exposure fields were all
            # null, and nothing said why). The engine returns the reason
            # itself (`RISK_BUDGET_MISSING`, `PORTFOLIO_CONTEXT_MISSING`), so
            # a plan that could not be quantified is refused for *that*
            # cause and not for one it happens to share with a valid plan.
            if not risk_blocked:
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
    #
    # When the graph's pre-check already ran (it carries its verdict in the
    # state), that verdict is REUSED rather than recomputed: the analysis
    # the managers saw and the gate's decision must be the same computation,
    # or a run could be debated as verified and then blocked, or worse the
    # reverse.
    freshness = None
    data_quality_blocked = False
    precheck = final_state.get("data_quality_precheck")
    if isinstance(precheck, dict) and precheck.get("blocks_execution"):
        data_quality_blocked = True
        freshness = _freshness_from_precheck(precheck)
    elif fundamentals_filings is not None:
        freshness = check_filing_freshness(
            used_fundamentals_period_end, fundamentals_filings, trade_date,
            used_period=used_fundamentals_period,
        )
        if freshness.blocks_decision:
            data_quality_blocked = True

    # P0.2: an unresolved cross-agent conflict over a material fact must
    # not feed an approval. The registry is populated automatically from
    # the run's own reports (labelled metric patterns only) when the
    # caller did not supply one; harvested facts are unverified by
    # construction — harvesting proves what an agent asserted, not that
    # it is true.
    registry = fact_registry_report
    if registry is None:
        harvested = harvest_facts({
            key: final_state.get(key)
            for key in ("market_report", "news_report", "sentiment_report",
                        "fundamentals_report")
            if isinstance(final_state.get(key), str)
        })
        if harvested:
            registry = register_facts(harvested)
    if registry is not None and registry.blocks_decision:
        data_quality_blocked = True

    # P0-B: recompute every percentage the report states from the dated
    # snapshot. A critical mismatch blocks: a report may round, it may not
    # contradict its own data. The snapshot's price/indicator dates must
    # also agree — two sessions mixed is not one snapshot.
    arithmetic_verdicts = []
    arithmetic_blocked = False
    if price_snapshot:
        alignment = check_price_timestamp_alignment(
            price_snapshot.get("price_as_of"),
            price_snapshot.get("indicator_as_of"),
            indicator=price_snapshot.get("indicator", "indicator"),
        )
        arithmetic_verdicts.append(alignment)
        if alignment.blocks_decision:
            arithmetic_blocked = True

        close = price_snapshot.get("close")
        for label, spec in (stated_percentages or {}).items():
            verdict = check_stated_percentage(
                spec.get("stated_pct"), spec.get("reference"), close,
                label=label,
            )
            arithmetic_verdicts.append(verdict)
            if verdict.blocks_decision:
                arithmetic_blocked = True
    if arithmetic_blocked:
        data_quality_blocked = True

    # Financial Math Engine (§9, §11): the plan's own numbers must hold up
    # arithmetically, and any numeric claim the reports make must either
    # match a verified metric or be reported unverifiable. A contradiction
    # here is a hard block, so it cannot be downgraded to a WAIT later.
    # §7: the constraint on agent arithmetic lives in code. Each analyst's
    # report is checked against the certified metrics, so a figure the engine
    # disproves blocks here rather than relying on a prompt asking the model
    # not to compute.
    report_validations = []
    reports_to_check = {
        "market": final_state.get("market_report"),
        "fundamentals": final_state.get("fundamentals_report"),
        "news": final_state.get("news_report"),
    }
    for agent_name, text in reports_to_check.items():
        if not isinstance(text, str) or not text:
            continue
        validation = validate_analyst_report(
            text, agent=agent_name, registry=metric_registry,
        )
        report_validations.append(validation)
        if validation.blocks_decision:
            data_quality_blocked = True

    math_verdict = None
    try:
        math_verdict = evaluate_math(
            registry=metric_registry,
            reports={
                key: final_state.get(key)
                for key in ("market_report", "news_report", "sentiment_report",
                            "fundamentals_report", "investment_plan",
                            "trader_investment_plan")
                if isinstance(final_state.get(key), str)
            } or None,
            entry=eff_entry,
            stop=eff_stop,
            atr=eff_atr,
            direction=eff_direction,
            stated_atr_distance=stated_atr_distance,
            strategic_rating=strategic.rating if strategic else None,
            authorized_orders=0,
            # No period comparison here: the accounting-period check needs a
            # *period end* on both sides, and ``trade_date`` is an analysis
            # date, not a fiscal period. Comparing the two flagged every run
            # whose report had no fundamentals section. The freshest-period
            # question is already answered by the filing freshness gate
            # above, which knows both periods.
        )
    except Exception:  # noqa: BLE001 — the math layer must not sink the run
        logger.exception("Financial math evaluation failed for %s on %s",
                         ticker, trade_date)

    math_reasons = math_verdict.reasons if math_verdict is not None else ()
    if math_reasons:
        data_quality_blocked = True

    # §4: an executable decision must rest on at least one certified metric.
    # Without a registry — or with one that certified nothing — the gate cannot
    # say the plan's numbers hold up, so it must not propose an order. The
    # report is still produced; only the order stops. This is the rule that
    # makes "no metric" block without turning "not computable" into a
    # contradiction (which is what broke every run before).
    certified = _certified_metric_count(metric_registry)
    if certified == 0:
        data_quality_blocked = True
        math_reasons = tuple(dict.fromkeys(
            tuple(math_reasons) + (GateReason.NO_CERTIFIED_METRIC,)))

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
        math_reasons=math_reasons,
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
    if registry is not None:
        record.fact_registry = registry
    if sizing is not None:
        record.exposure_sizing = sizing
        # F4: the quantity is the audit's answer to "how much would this
        # order have been". It used to be written only as
        # ``exposure_sizing``, so ``risk.qty_proposed`` reported null for a
        # plan that had in fact been sized.
        record.sizing = SizingResult(
            qty=sizing.qty,
            risk_per_share=abs(eff_entry - eff_stop)
            if eff_entry is not None and eff_stop is not None else 0.0,
            stressed_risk_per_share=(
                abs(eff_entry - eff_stop) / sizing.qty
                if sizing.qty > 0 and eff_entry is not None
                and eff_stop is not None else 0.0
            ),
            risk_budget=risk_budget or 0.0,
            planned_risk=sizing.planned_risk,
            reasons=sizing.reasons,
        )
    if arithmetic_verdicts:
        record.arithmetic_verdicts = arithmetic_verdicts
    if math_verdict is not None:
        record.math_verdict = math_verdict

    # §9: the audit must state whether the decision rested on a confirmed close
    # or on a bar still forming. Without this the three bar fields stay null and
    # a reader cannot tell an EOD analysis from an intraday one.
    if price_snapshot:
        bar_assessment = _assess_price_bar(price_snapshot, trade_date)
        if bar_assessment is not None:
            record.price_snapshot_bar = bar_assessment

    # P0-D: the structured, machine-readable execution verdict. It carries
    # the gate's action and every blocking reason; authorized_orders stays
    # empty unless the gate actually proposed an order (the verdict
    # constructor refuses the contradiction either way).
    authorized = ()
    if decision.creates_order and sizing is not None and sizing.qty > 0:
        authorized = ({"ticker": ticker, "quantity": sizing.qty,
                       "entry": eff_entry, "stop": eff_stop},)
    record.execution_verdict = verdict_from_gate(
        run_id=f"{ticker}-{trade_date}-{snapshot_id}",
        instrument=ticker,
        analysis_as_of=trade_date,
        strategic_rating=strategic.rating if strategic else "UNKNOWN",
        decision=decision,
        policy_version=_POLICY_VERSION,
        blocking_reasons=tuple(r.value for r in decision.reasons),
        authorized_orders=authorized,
    )
    return record, decision


def write_audit_record(record: AuditRecord, results_dir: str,
                       run_id: str | None = None) -> Path:
    """Write the audit JSON beside the run's state log.

    Named by analysis date *and* run id when one is supplied (§2 of P4): two
    analyses of one instrument on one day used to write the same filename, so
    the later run destroyed the earlier one — the lineage audit found three of
    its four runs missing for exactly this reason. The date stays in the name
    so an operator can still find an audit by day, and the id is what keeps
    them apart.
    """
    safe = record.ticker.replace("/", "-")
    directory = Path(results_dir) / safe / "reliability_audit"
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"audit_{record.analysis_as_of}"
    if run_id:
        stem = f"{stem}_{run_id}"
    path = directory / f"{stem}.json"
    path.write_text(record.to_json(), encoding="utf-8")
    return path


def attach_to_state(final_state: dict, decision: GateDecision) -> None:
    """Attach the gate's verdict to the run state for callers and the CLI."""
    final_state["execution_action"] = decision.action.value
    final_state["execution_reason_codes"] = [r.value for r in decision.reasons]
    final_state["execution_authorization"] = _authorization(
        decision, final_state.get("execution_authorization"))


class ReportOutcome(StrEnum):
    """Whether the analysis itself produced a usable document (§4).

    Separate from the execution verdict on purpose: a run whose numbers cannot
    be certified still owes its reader an explanation of what went wrong. Failing
    the whole run would hide the diagnosis; approving the order would act on it.
    """

    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class ExecutionAuthorization(StrEnum):
    """Whether an order may be created (§4)."""

    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


def _authorization(decision: GateDecision, previous: Any) -> str:
    """The execution authorisation implied by a gate decision.

    ``APPROVED`` only when the gate actually proposes an order. A ``WAIT`` is
    ``NOT_APPLICABLE`` — the plan is sound but it is not time to act, which is
    not a refusal. Everything else is ``BLOCKED``.
    """
    if decision.creates_order:
        return str(ExecutionAuthorization.APPROVED)
    if decision.action is ExecutionAction.WAIT:
        return str(ExecutionAuthorization.NOT_APPLICABLE)
    return str(ExecutionAuthorization.BLOCKED)


def _certified_metric_count(registry: Any) -> int:
    """How many metrics this run certified, or 0 when there is no registry.

    Reads the registry's own ``usable`` list rather than re-deriving the rule,
    so "certified" means exactly what the registry says it means.
    """
    if registry is None:
        return 0
    try:
        return len(registry.usable)
    except Exception:  # noqa: BLE001 — an unreadable registry certified nothing
        return 0


def report_outcome(math_verdict: Any, decision: GateDecision,
                   registry: Any) -> str:
    """Whether the run produced a report, and whether it carries warnings (§4).

    ``COMPLETED`` — every check that ran passed.
    ``COMPLETED_WITH_WARNINGS`` — the report is usable but something could not be
    certified or was contradicted; the reader is told, and execution is blocked.
    ``FAILED`` — no report content at all.

    Deliberately independent of the gate's action: a blocked order and a
    delivered report are both correct outcomes of the same run.
    """
    if not decision.ticker:
        return str(ReportOutcome.FAILED)
    problems = False
    if math_verdict is not None:
        findings = getattr(getattr(math_verdict, "report", None), "findings", [])
        # A finding that passed its check is not a warning: a claim matching the
        # engine is the healthy case, and counting it would mark every good run
        # as warning-laden.
        problems = any(
            getattr(f, "blocks", False)
            or str(getattr(f, "kind", "")) == "UNVERIFIED"
            for f in findings
        )
    if registry is not None:
        try:
            problems = problems or bool(registry.blocking)
        except Exception:  # noqa: BLE001 — a registry that cannot be read is a warning
            problems = True
    return str(ReportOutcome.COMPLETED_WITH_WARNINGS if problems
               else ReportOutcome.COMPLETED)


def attach_registry_status(final_state: dict, registry: Any) -> None:
    """Publish what this run certified, and the two separate outcomes (§4).

    Written into the state so the caller, the CLI and the audit can all say
    *how many metrics were certified* and *whether the order was authorised* —
    two different questions that the earlier code answered with one flag.
    """
    from tradingagents.dataflows.math.run_registry import status_of

    if registry is None:
        final_state["metric_registry_status"] = {
            "metrics_total": 0, "metrics_usable": 0,
            "metrics_not_computable": 0, "blocking_metrics": [],
            "is_empty": True, "source": None,
            "note": "no registry was available: nothing was certified",
        }
    else:
        try:
            final_state["metric_registry_status"] = status_of(registry)
        except Exception:  # noqa: BLE001 — an unreadable registry is reported, not fatal
            final_state["metric_registry_status"] = {
                "is_empty": True, "note": "the registry could not be read"}

    decision = final_state.get("execution_action")
    blocking = final_state.get("execution_reason_codes") or []
    # A run with no certified metric and no blocking reason still must not
    # authorise an order: an unverified decision is not an approved one.
    status = final_state.get("metric_registry_status") or {}
    if not status.get("metrics_usable") and decision == "PROPOSE_PAPER_ORDER":
        final_state["execution_authorization"] = str(
            ExecutionAuthorization.BLOCKED)
        final_state["execution_reason_codes"] = list(
            dict.fromkeys(list(blocking) + ["NO_CERTIFIED_METRIC"]))
    elif "execution_authorization" not in final_state:
        final_state["execution_authorization"] = str(
            ExecutionAuthorization.NOT_APPLICABLE)

    # A plan that proposed cleanly carries "OK" as its only reason, which is a
    # success code, not a warning. Only a genuine refusal makes the report
    # "completed with warnings".
    _non_blocking = {"OK", "NO_TRIGGER", "ENTRY_TRIGGER_NOT_MET", "MARKET_CLOSED"}
    warnings = [c for c in blocking if c not in _non_blocking]
    final_state["report_outcome"] = str(
        ReportOutcome.COMPLETED_WITH_WARNINGS if warnings
        else ReportOutcome.COMPLETED
    )
