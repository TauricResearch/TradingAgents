"""Deterministic Safety Gate: the authority boundary after the Portfolio Manager.

The Portfolio Manager is an LLM; its rating is advisory. This node is the
deterministic authority that decides whether that rating may leave the graph as a
tradeable call. It makes no model, tool or vendor call: it only checks that the
decision is backed by the evidence the configured workflow actually produced.

A tradeable rating is preserved only when every selected analyst's report and the
investment plan, trader plan and final decision are non-empty. Any gap downgrades
the run to REVIEW with stable reason codes (INV-SG-01). The gate is monotonic: it
preserves a canonical 5-tier rating or downgrades to REVIEW, never upgrading REVIEW
or swapping one tradeable tier for another (INV-SG-02). Any unexpected error fails
closed to REVIEW / GATE_ERROR.
"""

from __future__ import annotations

import logging

from tradingagents.agents.rating import RATING_REVIEW, RATINGS_5_TIER, extract_rating
from tradingagents.graph.analyst_execution import build_analyst_execution_plan

logger = logging.getLogger(__name__)

PASS = "PASS"
REVIEW = "REVIEW"

# Stable, ordered reason codes. The order here is the order they are reported in.
MISSING_SELECTED_EVIDENCE = "MISSING_SELECTED_EVIDENCE"
MISSING_INVESTMENT_PLAN = "MISSING_INVESTMENT_PLAN"
MISSING_TRADER_PLAN = "MISSING_TRADER_PLAN"
MISSING_DECISION = "MISSING_DECISION"
UNUSABLE_RATING = "UNUSABLE_RATING"
GATE_ERROR = "GATE_ERROR"

_RATING_SET = set(RATINGS_5_TIER)


def _present(value) -> bool:
    """Existence only: a non-blank string. Non-strings count as missing."""
    return isinstance(value, str) and value.strip() != ""


def _effective_rating(state) -> str | None:
    """The rating the decision carries, or ``None`` when it is not recoverable.

    A present ``final_rating`` is authoritative: if it is not a canonical 5-tier
    rating it is unusable, even when the prose parses (no silent upgrade). Only an
    absent ``final_rating`` is recovered from ``final_trade_decision`` via the frozen
    parser, so an older checkpoint still works.
    """
    if "final_rating" in state:
        rating = state["final_rating"]
        return rating if isinstance(rating, str) and rating in _RATING_SET else None
    return extract_rating(state.get("final_trade_decision") or "")


def _already_gated(state) -> bool:
    """Whether this state already carries a Safety Gate REVIEW from an earlier pass."""
    return state.get("safety_gate_status") == REVIEW and state.get("final_rating") == RATING_REVIEW


def evaluate_safety(state, selected_analysts):
    """Evaluate a final decision against the configured evidence; return partial state.

    Returns only the gate's additive keys; ``final_trade_decision`` is never touched.
    A state already carrying a Safety Gate REVIEW is returned unchanged, so a second
    evaluation is idempotent.
    """
    try:
        return _evaluate(state, selected_analysts)
    except Exception as exc:  # noqa: BLE001 - fail closed on any unexpected error
        logger.warning("Safety Gate failed; downgrading to REVIEW: %s", exc)
        return _review((), (GATE_ERROR,))


def _evaluate(state, selected_analysts):
    if _already_gated(state):
        return _review(tuple(state.get("safety_gate_missing_evidence") or ()),
                       tuple(state.get("safety_gate_reason_codes") or ()))

    reasons: list[str] = []
    missing: list[str] = []

    report_keys = [spec.report_key for spec in build_analyst_execution_plan(selected_analysts).specs]
    for key in report_keys:
        if not _present(state.get(key)):
            missing.append(key)
    if missing:
        reasons.append(MISSING_SELECTED_EVIDENCE)

    for key, code in (("investment_plan", MISSING_INVESTMENT_PLAN),
                      ("trader_investment_plan", MISSING_TRADER_PLAN),
                      ("final_trade_decision", MISSING_DECISION)):
        if not _present(state.get(key)):
            reasons.append(code)

    rating = _effective_rating(state)
    if rating is None:
        reasons.append(UNUSABLE_RATING)

    if reasons:
        return _review(tuple(missing), tuple(reasons))
    return {
        "final_rating": rating,
        "safety_gate_status": PASS,
        "safety_gate_reason_codes": (),
        "safety_gate_missing_evidence": (),
    }


def _review(missing: tuple, reasons: tuple) -> dict:
    return {
        "final_rating": RATING_REVIEW,
        "safety_gate_status": REVIEW,
        "safety_gate_reason_codes": reasons,
        "safety_gate_missing_evidence": missing,
    }


def create_safety_gate(selected_analysts):
    """The graph's Safety Gate node, bound to the run's selected analysts."""
    selected = tuple(selected_analysts)

    def safety_gate_node(state) -> dict:
        return evaluate_safety(state, selected)

    return safety_gate_node
