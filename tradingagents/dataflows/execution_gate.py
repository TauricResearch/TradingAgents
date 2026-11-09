"""Execution Gate (Phase 3, contract section 4).

The final deterministic check between a proposed plan and any paper order.
LLM output — ratings, theses, enthusiasm — never reaches this module: it
consumes only the typed verdicts of the earlier phases (provenance, causal
guard, validator, risk engine) plus the portfolio context, and answers one
question: may a paper order be submitted *right now*?

Hard rules, per the contract:

- ``WAIT`` means no trigger has fired yet; ``BLOCK`` means the plan is
  invalid or mandatory data is missing. **Neither creates any order**, not
  even a pending conditional one.
- A strategic rating (``OVERWEIGHT``/``BUY`` in prose) is never an
  executable action: the rating vocabulary and the action vocabulary share
  no member, and the mapping between them is explicit.
- Every submission requires a final revalidation immediately before it:
  session state, price freshness, idempotency key, exposure, updated
  conditions. A stale signal is re-checked or refused, never trusted from
  a historical report.
- Idempotency: the same plan key can never produce two orders. Retries
  return the original outcome.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum

from tradingagents.dataflows.causal_guard import (
    NOT_YET_OBSERVABLE,
    OBSERVABLE_INTRADAY,
)
from tradingagents.dataflows.risk_engine import RiskReason, portfolio_risk_check


class ExecutionAction(StrEnum):
    """The contract's full action vocabulary (§4). This module emits only
    WAIT/BLOCK/PROPOSE — an actual ``SUBMIT_PAPER_ORDER`` happens through
    :meth:`ExecutionGate.submit`, which revalidates and is idempotent; the
    member exists so decision records can name the submission step."""

    WAIT = "WAIT"
    BLOCK = "BLOCK"
    PROPOSE_PAPER_ORDER = "PROPOSE_PAPER_ORDER"
    SUBMIT_PAPER_ORDER = "SUBMIT_PAPER_ORDER"


class GateReason(StrEnum):
    """Machine-readable reasons, stable for the audit trail and reports."""

    OK = "OK"
    NO_TRIGGER = "NO_TRIGGER"
    ENTRY_TRIGGER_NOT_MET = "ENTRY_TRIGGER_NOT_MET"
    POST_EARNINGS_REACTION_UNOBSERVABLE = "POST_EARNINGS_REACTION_UNOBSERVABLE"
    PORTFOLIO_RISK_BUDGET_MISSING = "PORTFOLIO_RISK_BUDGET_MISSING"
    PORTFOLIO_RISK_BUDGET_EXCEEDED = "PORTFOLIO_RISK_BUDGET_EXCEEDED"
    RISK_PLAN_BLOCKED = "RISK_PLAN_BLOCKED"
    DATA_QUALITY_BLOCKED = "DATA_QUALITY_BLOCKED"
    STALE_SIGNAL = "STALE_SIGNAL"
    MARKET_CLOSED = "MARKET_CLOSED"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    # Financial Math Engine verdicts (§11). Each names a specific
    # mathematical hazard, so a blocked order says *which* number was wrong
    # rather than only that something was.
    INVALID_PRICE_TO_BOOK = "INVALID_PRICE_TO_BOOK"
    INVALID_STOP_ATR_DISTANCE = "INVALID_STOP_ATR_DISTANCE"
    INVALID_VALUATION_METRIC = "INVALID_VALUATION_METRIC"
    NUMERIC_CLAIM_CONTRADICTED = "NUMERIC_CLAIM_CONTRADICTED"
    NUMERIC_CLAIM_UNVERIFIABLE = "NUMERIC_CLAIM_UNVERIFIABLE"
    # §3: a percentage an agent stated that the engine recomputes differently.
    # Distinct from CONTRADICTED, which covers a stated multiple: this one is
    # specifically a claimed rate (growth, contraction, distance) that the
    # registry disproves.
    NUMERIC_CLAIM_MISMATCH = "NUMERIC_CLAIM_MISMATCH"
    STALE_FUNDAMENTALS_PERIOD = "STALE_FUNDAMENTALS_PERIOD"


# Strategic ratings (contract §4 level 1). Disjoint from ExecutionAction by
# construction — asserted by the Phase 0 baseline tests.
STRATEGIC_RATINGS = frozenset({"UNDERWEIGHT", "NEUTRAL", "OVERWEIGHT"})

# Investment intents (contract §4 level 2).
INVESTMENT_INTENTS = frozenset({
    "AVOID", "MONITOR", "ACCUMULATE_CONDITIONALLY", "MAINTAIN", "REDUCE",
})

# Ratings that may *propose* a paper order once every other check passes.
# OVERWEIGHT proposes; it never executes by itself.
_RATINGS_ELIGIBLE_TO_PROPOSE = frozenset({"OVERWEIGHT"})

# Intents that may propose; conditional accumulation still needs its trigger.
_INTENTS_ELIGIBLE_TO_PROPOSE = frozenset({"ACCUMULATE_CONDITIONALLY"})


@dataclass(frozen=True)
class PlanInput:
    """What the gate evaluates: the plan as proposed, plus phase verdicts.

    ``rating`` and ``intent`` come from the decision layer; ``risk_blocked``
    and ``risk_reasons`` from the Phase 2 engine; ``data_quality_blocked``
    from the Phase 1 validator (quarantined metrics, unresolved conflicts);
    ``post_event_status`` from the causal guard; ``trigger_met`` states
    whether the plan's own entry condition is satisfied *now*; ``signal_as_of``
    is when the signal was computed, so staleness is checkable.
    """

    ticker: str
    rating: str
    intent: str
    trigger_met: bool
    risk_blocked: bool
    risk_reasons: tuple[RiskReason, ...] = ()
    data_quality_blocked: bool = False
    post_event_status: str | None = None
    signal_as_of: str | None = None          # YYYY-MM-DD or None
    analysis_as_of: str | None = None        # YYYY-MM-DD or None
    market_open: bool = True
    # Financial Math Engine verdicts (§11). ``math_reasons`` carries the
    # specific hazards the engine detected (INVALID_PRICE_TO_BOOK,
    # INVALID_STOP_ATR_DISTANCE, contradicted numeric claims, ...). They are
    # *hard* blocks: a mathematical contradiction is not a "not yet".
    math_reasons: tuple[GateReason, ...] = ()


@dataclass(frozen=True)
class GateDecision:
    """The gate's answer: an action plus machine-readable reasons."""

    action: ExecutionAction
    reasons: tuple[GateReason, ...]
    ticker: str

    @property
    def creates_order(self) -> bool:
        """WAIT and BLOCK create zero orders — the contract's core promise."""
        return self.action is ExecutionAction.PROPOSE_PAPER_ORDER


def evaluate_plan(plan: PlanInput) -> GateDecision:
    """Run the policy checks over a proposed plan.

    Order of checks matters for the reason codes reported, not for safety:
    any failing check blocks or waits regardless of the others.
    """
    reasons: list[GateReason] = []

    # Vocabulary check first: an unknown rating/intent is a schema violation.
    if plan.rating not in STRATEGIC_RATINGS or plan.intent not in INVESTMENT_INTENTS:
        return GateDecision(ExecutionAction.BLOCK, (GateReason.DATA_QUALITY_BLOCKED,),
                            plan.ticker)

    # Data quality (Phase 1): quarantined metrics or unresolved conflicts.
    if plan.data_quality_blocked:
        reasons.append(GateReason.DATA_QUALITY_BLOCKED)

    # Financial Math Engine (§11): a contradicted multiple, a stop distance
    # that does not match its own entry/ATR, or an unverifiable critical
    # claim. Appended before the "not yet" logic so these can never be
    # downgraded to a WAIT — a wrong number does not become right later.
    reasons.extend(plan.math_reasons)

    # Causal guard (Phase 1): a reaction claim needs a post-event session.
    # When the trigger is already met the plan would act *now* on a reaction
    # that cannot be verified: that is the contract's hard BLOCK ("when the
    # strategy relies on the presumed reaction"). When the trigger is unmet
    # the plan is not acting on the reaction yet, so it is a WAIT reason —
    # the contract's own example schema carries this code inside a WAIT.
    reaction_unobservable = plan.post_event_status in (
        NOT_YET_OBSERVABLE, OBSERVABLE_INTRADAY)
    if reaction_unobservable and plan.trigger_met:
        reasons.append(GateReason.POST_EARNINGS_REACTION_UNOBSERVABLE)

    # Risk engine (Phase 2): the plan's own verdict leads.
    if plan.risk_blocked:
        reasons.append(GateReason.RISK_PLAN_BLOCKED)
        reasons.extend(_risk_reason_mapping(plan.risk_reasons))

    # Staleness: a signal computed before the analysis date is a historical
    # report, not a live signal — recompute or refuse (contract §7).
    if plan.signal_as_of and plan.analysis_as_of and plan.signal_as_of < plan.analysis_as_of:
        reasons.append(GateReason.STALE_SIGNAL)

    # Session: proposals require an open market; WAIT otherwise.
    if not plan.market_open:
        reasons.append(GateReason.MARKET_CLOSED)

    # The plan's own trigger: not met is a WAIT reason, not a BLOCK — the
    # plan may be valid, it just is not time yet.
    if not plan.trigger_met:
        reasons.append(GateReason.ENTRY_TRIGGER_NOT_MET)
        # Still reported: when the trigger eventually fires, this same plan
        # will hit the hard block below until a post-event session exists.
        if reaction_unobservable:
            reasons.append(GateReason.POST_EARNINGS_REACTION_UNOBSERVABLE)
    elif reaction_unobservable:
        # Trigger met on an unobservable reaction: the hard block, applied
        # here so the WAIT/BLOCK split above stays readable.
        reasons.append(GateReason.POST_EARNINGS_REACTION_UNOBSERVABLE)

    # A reason blocks unless it is a "not yet" condition: an unmet trigger,
    # a closed market, or an unobservable reaction while the trigger is
    # itself unmet (the plan is not acting on the reaction yet).
    not_yet = {GateReason.ENTRY_TRIGGER_NOT_MET, GateReason.MARKET_CLOSED}
    if GateReason.ENTRY_TRIGGER_NOT_MET in reasons:
        not_yet.add(GateReason.POST_EARNINGS_REACTION_UNOBSERVABLE)
    blocking = [r for r in reasons if r not in not_yet]
    if blocking:
        return GateDecision(ExecutionAction.BLOCK, tuple(reasons), plan.ticker)

    if reasons:
        return GateDecision(ExecutionAction.WAIT, tuple(reasons), plan.ticker)

    # Everything passed: the rating/intent pair must still be eligible to
    # propose. OVERWEIGHT + ACCUMULATE_CONDITIONALLY proposes; anything
    # else (MONITOR, MAINTAIN, ...) waits by policy.
    if (plan.rating in _RATINGS_ELIGIBLE_TO_PROPOSE
            and plan.intent in _INTENTS_ELIGIBLE_TO_PROPOSE):
        return GateDecision(ExecutionAction.PROPOSE_PAPER_ORDER, (GateReason.OK,),
                            plan.ticker)
    return GateDecision(ExecutionAction.WAIT, (GateReason.NO_TRIGGER,), plan.ticker)


def _risk_reason_mapping(risk_reasons: tuple[RiskReason, ...]) -> tuple[GateReason, ...]:
    """Map the risk engine's reasons onto gate reasons for the audit trail."""
    mapping = {
        RiskReason.RISK_BUDGET_MISSING: GateReason.PORTFOLIO_RISK_BUDGET_MISSING,
        RiskReason.PORTFOLIO_CONTEXT_MISSING: GateReason.PORTFOLIO_RISK_BUDGET_MISSING,
        RiskReason.RISK_BUDGET_EXCEEDED: GateReason.PORTFOLIO_RISK_BUDGET_EXCEEDED,
    }
    return tuple(mapping[r] for r in risk_reasons if r in mapping)


# ---------------------------------------------------------------------------
# Idempotent paper-order submission
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperOrder:
    """A simulated order. Broker-neutral: no venue, no live path."""

    order_id: str
    idempotency_key: str
    ticker: str
    quantity: int
    limit_price: float | None
    created_from_decision: GateDecision


@dataclass
class ExecutionGate:
    """Holds the idempotency ledger and revalidates before any submission.

    One gate per run. ``submit`` is the only way a paper order comes to
    exist, and it requires a fresh ``PROPOSE_PAPER_ORDER`` decision — a
    historical one is refused (``STALE_SIGNAL``), because conditions must be
    revalidated at execution time, not trusted from a report.
    """

    analysis_as_of: str
    _orders_by_key: dict[str, PaperOrder] = field(default_factory=dict)

    def plan_key(self, plan: PlanInput) -> str:
        """A stable key for the plan: same inputs, same key, one order ever."""
        payload = json.dumps({
            "ticker": plan.ticker,
            "rating": plan.rating,
            "intent": plan.intent,
            "analysis_as_of": self.analysis_as_of,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def submit(
        self,
        plan: PlanInput,
        decision: GateDecision,
        quantity: int,
        limit_price: float | None = None,
    ) -> tuple[PaperOrder | None, GateReason]:
        """Attempt a paper submission; idempotent and revalidation-gated.

        Returns ``(order, reason)``. ``order`` is None unless a new order
        was actually created; a retry with the same plan key returns the
        original order with ``DUPLICATE_ORDER`` instead of a second one.
        """
        # Revalidation 1: the decision must be a fresh proposal for this run.
        if decision.action is not ExecutionAction.PROPOSE_PAPER_ORDER:
            return None, (GateReason.NO_TRIGGER if decision.action is ExecutionAction.WAIT
                          else GateReason.RISK_PLAN_BLOCKED)
        if decision.ticker != plan.ticker:
            return None, GateReason.DATA_QUALITY_BLOCKED

        # Revalidation 2: the signal must be current at submission time.
        if (plan.signal_as_of and plan.signal_as_of < self.analysis_as_of) \
                or (plan.analysis_as_of and plan.analysis_as_of < self.analysis_as_of):
            return None, GateReason.STALE_SIGNAL

        # Revalidation 3: quantity must be positive and finite — no zero or
        # negative "orders".
        if quantity <= 0:
            return None, GateReason.RISK_PLAN_BLOCKED

        key = self.plan_key(plan)
        existing = self._orders_by_key.get(key)
        if existing is not None:
            # Idempotency: the retry returns the original order, no new one.
            return existing, GateReason.DUPLICATE_ORDER

        order = PaperOrder(
            order_id=f"paper-{key}-{len(self._orders_by_key) + 1}",
            idempotency_key=key,
            ticker=plan.ticker,
            quantity=quantity,
            limit_price=limit_price,
            created_from_decision=decision,
        )
        self._orders_by_key[key] = order
        return order, GateReason.OK

    def orders(self) -> list[PaperOrder]:
        """Every order this gate created, in creation order."""
        return list(self._orders_by_key.values())


def check_portfolio_budget(planned_risk: float | None, equity: float | None,
                           max_loss_fraction: float | None = None) -> GateDecision:
    """A convenience pass-through: the portfolio check as a gate decision.

    Wraps the Phase 2 ``portfolio_risk_check`` so callers get one vocabulary.
    """
    check = portfolio_risk_check(planned_risk, equity, max_loss_fraction)
    if check.blocked:
        reasons = _risk_reason_mapping(check.reasons) or (GateReason.RISK_PLAN_BLOCKED,)
        return GateDecision(ExecutionAction.BLOCK, reasons, ticker="")
    return GateDecision(ExecutionAction.WAIT, (GateReason.OK,), ticker="")
