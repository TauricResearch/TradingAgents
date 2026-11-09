"""Mathematical execution gate (§11): the engine's verdict as gate reasons.

The Execution Gate already refuses to propose an order when a *policy* check
fails. This module supplies the *mathematical* checks that gate needs, and
translates them into the reason codes the gate and the audit already speak,
so a blocked order names the specific number that was wrong.

The mapping is deliberately narrow and explicit:

===============================  ==================================
engine finding                    gate reason
===============================  ==================================
P/B contradicted or refused      ``INVALID_PRICE_TO_BOOK``
stop distance ≠ entry/ATR        ``INVALID_STOP_ATR_DISTANCE``
stop on the wrong side           ``RISK_PLAN_BLOCKED``
any other refused valuation      ``INVALID_VALUATION_METRIC``
contradicted numeric claim       ``NUMERIC_CLAIM_CONTRADICTED``
unverifiable critical claim      ``NUMERIC_CLAIM_UNVERIFIABLE``
metric from a stale period       ``STALE_FUNDAMENTALS_PERIOD``
===============================  ==================================

Nothing here decides *whether* to trade — that stays with the gate and the
portfolio policy. This module only answers "is the arithmetic sound?", and
its answer is a list of reasons: empty means the numbers hold up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tradingagents.dataflows.execution_gate import GateReason
from tradingagents.dataflows.math.consistency import (
    ConsistencyReport,
    check_report_consistency,
    check_stop_consistency,
)
from tradingagents.dataflows.math.metric_record import MetricRecord
from tradingagents.dataflows.math.registry import MetricRegistry

# Metric names whose failure is reported as a P/B hazard specifically, so
# the operator sees which valuation broke rather than a generic refusal.
_PRICE_TO_BOOK_METRICS = frozenset({
    "price_to_book", "price_to_book_A", "price_to_book_B",
})

# Consistency finding code -> gate reason. Anything unlisted but blocking
# becomes ``DATA_QUALITY_BLOCKED``: unknown arithmetic failure still blocks,
# it just does not claim to be a specific hazard.
_FINDING_TO_REASON = {
    "INVALID_STOP_ATR_DISTANCE": GateReason.INVALID_STOP_ATR_DISTANCE,
    "STOP_WRONG_SIDE": GateReason.RISK_PLAN_BLOCKED,
    "CROSS_AGENT_NUMERIC_CONFLICT": GateReason.NUMERIC_CLAIM_CONTRADICTED,
    "RATING_ORDER_CONFLICT": GateReason.DATA_QUALITY_BLOCKED,
    "STALE_PERIOD_MIXING": GateReason.STALE_FUNDAMENTALS_PERIOD,
    "SHARE_CLASS_MIX": GateReason.INVALID_VALUATION_METRIC,
    "NUMERIC_CLAIM_MISMATCH": GateReason.NUMERIC_CLAIM_MISMATCH,
    "NUMERIC_CLAIM_NOT_CHECKABLE": GateReason.NUMERIC_CLAIM_UNVERIFIABLE,
    "STOP_DISTANCE_UNVERIFIED": GateReason.NUMERIC_CLAIM_UNVERIFIABLE,
}


@dataclass
class MathVerdict:
    """The engine's contribution to one run's gate decision."""

    reasons: tuple[GateReason, ...] = field(default_factory=tuple)
    report: ConsistencyReport = field(default_factory=ConsistencyReport)

    @property
    def blocks(self) -> bool:
        return bool(self.reasons)

    def summary(self) -> dict:
        return {
            "status": "BLOCKED" if self.blocks else "OK",
            "reasons": [str(r) for r in self.reasons],
            "consistency": self.report.summary(),
        }


def _metric_reason(record: MetricRecord) -> GateReason:
    """The most specific gate reason for a refused metric."""
    if record.metric in _PRICE_TO_BOOK_METRICS:
        return GateReason.INVALID_PRICE_TO_BOOK
    return GateReason.INVALID_VALUATION_METRIC


def evaluate_math(
    *,
    registry: MetricRegistry | None = None,
    reports: dict[str, str] | None = None,
    computed_metrics: dict[str, Any] | None = None,
    extracted_claims: dict[str, dict[str, list[Any]]] | None = None,
    entry: Any = None,
    stop: Any = None,
    atr: Any = None,
    direction: str = "LONG",
    stated_atr_distance: Any = None,
    strategic_rating: str | None = None,
    execution_action: str | None = None,
    authorized_orders: int = 0,
    metric_period: str | None = None,
    reference_period: str | None = None,
    metric_name: str = "metric",
    price_class: str | None = None,
    value_class: str | None = None,
) -> MathVerdict:
    """Run every mathematical check and return the gate's reason codes.

    ``computed_metrics`` defaults to the registry's verified values, so the
    claims checker can only ever compare against numbers the engine stands
    behind — never against another agent's prose.
    """
    if computed_metrics is None and registry is not None:
        computed_metrics = registry.verification_map()

    report = check_report_consistency(
        reports=reports,
        computed_metrics=computed_metrics,
        metrics=registry.blocking if registry is not None else None,
        extracted_claims=extracted_claims,
        entry=entry, stop=stop, atr=atr, direction=direction,
        stated_atr_distance=stated_atr_distance,
        strategic_rating=strategic_rating,
        execution_action=execution_action,
        authorized_orders=authorized_orders,
        metric_period=metric_period, reference_period=reference_period,
        metric_name=metric_name,
        price_class=price_class, value_class=value_class,
    )

    reasons: list[GateReason] = []
    for finding in report.findings:
        if not finding.blocks:
            continue
        reasons.append(_FINDING_TO_REASON.get(
            finding.code, GateReason.DATA_QUALITY_BLOCKED))

    if registry is not None:
        for record in registry.blocking:
            reasons.append(_metric_reason(record))

    # De-duplicate while preserving the order the checks ran in.
    return MathVerdict(
        reasons=tuple(dict.fromkeys(reasons)),
        report=report,
    )


def stop_only_math_verdict(entry: Any, stop: Any, atr: Any, *,
                           direction: str = "LONG",
                           stated_atr_distance: Any = None) -> MathVerdict:
    """The stop-distance check alone, for callers that need only that.

    Used by the risk wiring: the plan's own numbers are already extracted,
    and the question is whether the distance the report states matches
    them.
    """
    finding = check_stop_consistency(
        entry, stop, atr, direction=direction,
        stated_atr_distance=stated_atr_distance,
    )
    report = ConsistencyReport()
    reasons: list[GateReason] = []
    if finding is not None:
        report.findings.append(finding)
        if finding.blocks:
            reasons.append(_FINDING_TO_REASON.get(
                finding.code, GateReason.DATA_QUALITY_BLOCKED))
    return MathVerdict(reasons=tuple(reasons), report=report)
