"""Report consistency checker (§10): cross-agent numeric reconciliation.

Analysts may disagree about the *interpretation*; they may not present two
incompatible arithmetic results as equally true. This module runs before the
final report and looks for exactly that — the same metric computed or stated
differently by different agents, a valuation that contradicts its own
inputs, a stop distance that does not match its entry and ATR, a rating and
an order proposal that disagree.

The output is a structured diagnostic section, not an exception: the report
keeps every analyst's view and gains a list of what did not reconcile. What
it must never do is print a number the engine refused as though it were
verified.

Findings are graded. A ``CONTRADICTION`` blocks execution; an
``INCONSISTENCY`` is a difference inside tolerance that should be explained;
an ``UNVERIFIED`` finding is a claim nobody could check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from tradingagents.dataflows.math.claims import ClaimsReport, check_reports
from tradingagents.dataflows.math.metric_record import MetricRecord
from tradingagents.dataflows.math.precision import (
    PERCENT_QUANTUM,
    RATIO_QUANTUM,
    as_decimal,
    quantize,
)
from tradingagents.dataflows.math.technical import atr_distance


class FindingKind(StrEnum):
    """How bad a cross-report inconsistency is."""

    CONTRADICTION = "CONTRADICTION"    # mutually exclusive numbers: blocks
    INCONSISTENCY = "INCONSISTENCY"    # a difference needing explanation
    UNVERIFIED = "UNVERIFIED"          # nothing to check the figure against


@dataclass(frozen=True)
class Finding:
    """One cross-agent inconsistency, with the values that disagree."""

    kind: FindingKind
    code: str
    message: str
    agents: tuple[str, ...] = ()
    values: tuple[str, ...] = ()
    blocks: bool = False

    def summary(self) -> dict:
        return {
            "kind": str(self.kind),
            "code": self.code,
            "message": self.message,
            "agents": list(self.agents),
            "values": list(self.values),
            "blocks": self.blocks,
        }


@dataclass
class ConsistencyReport:
    """The diagnostic section the final report carries."""

    findings: list[Finding] = field(default_factory=list)
    claims: ClaimsReport | None = None
    metrics: list[MetricRecord] = field(default_factory=list)

    @property
    def contradictions(self) -> list[Finding]:
        return [f for f in self.findings if f.kind is FindingKind.CONTRADICTION]

    @property
    def blocks_decision(self) -> bool:
        """Whether the run may proceed to an executable decision.

        Any contradiction blocks. A refused or contradicted metric blocks
        too: it means a number in the report is known to be wrong. An
        unverifiable claim blocks only when a claim checker flagged it —
        that judgement lives in ``ClaimsReport``.
        """
        if any(f.blocks for f in self.findings):
            return True
        if any(m.blocks_decision for m in self.metrics):
            return True
        return bool(self.claims and self.claims.blocks_decision)

    @property
    def blocking_codes(self) -> tuple[str, ...]:
        codes: list[str] = []
        for finding in self.findings:
            if finding.blocks:
                codes.append(finding.code)
        for record in self.metrics:
            if record.blocks_decision:
                codes.append(record.metric.upper())
        if self.claims:
            codes.extend(self.claims.blocking_labels)
        return tuple(dict.fromkeys(codes))

    def summary(self) -> dict:
        return {
            "status": "BLOCKED" if self.blocks_decision else (
                "OK" if self.findings or self.metrics else None),
            "blocking_codes": list(self.blocking_codes),
            "findings": [f.summary() for f in self.findings],
            "claims": self.claims.summary() if self.claims else None,
            "metrics": [m.summary() for m in self.metrics],
        }


def cross_agent_numeric_consistency(
    reports: dict[str, str],
    extracted: dict[str, dict[str, list[Any]]] | None = None,
) -> list[Finding]:
    """Find the same labelled metric stated differently by two agents.

    ``extracted`` maps agent -> metric label -> list of the numeric values
    that agent stated. Two agents disagreeing beyond tolerance on the *same*
    labelled metric is a contradiction: they cannot both be right about the
    same number, and the report must not present both as verified.

    Comparing prose numbers is a last resort — the preferred path is agents
    emitting structured metrics — so this function only uses values that
    carry an explicit label.
    """
    findings: list[Finding] = []
    if not extracted:
        return findings

    labels: set[str] = set()
    for per_agent in extracted.values():
        labels.update(per_agent.keys())

    for label in sorted(labels):
        stated: list[tuple[str, Decimal]] = []
        for agent, per_agent in extracted.items():
            for raw in per_agent.get(label, []):
                value = as_decimal(raw)
                if value is not None:
                    stated.append((agent, value))
        if len({value for _, value in stated}) < 2:
            continue
        low = min(value for _, value in stated)
        high = max(value for _, value in stated)
        # Percentage points for percentages, absolute for multiples.
        tolerance = (PERCENT_QUANTUM * 10 if label.startswith("distance")
                     else RATIO_QUANTUM * 200)
        if (high - low) <= tolerance:
            continue
        findings.append(Finding(
            kind=FindingKind.CONTRADICTION,
            code="CROSS_AGENT_NUMERIC_CONFLICT",
            message=(f"the same metric '{label}' is stated differently across "
                     f"agents: {quantize(low, PERCENT_QUANTUM)} to "
                     f"{quantize(high, PERCENT_QUANTUM)} — these cannot both "
                     "be true"),
            agents=tuple(dict.fromkeys(agent for agent, _ in stated)),
            values=(str(low), str(high)),
            blocks=True,
        ))
    return findings


def check_stop_consistency(entry: Any, stop: Any, atr: Any, *,
                           direction: str = "LONG",
                           stated_atr_distance: Any = None,
                           tolerance: Decimal = Decimal("0.1")) -> Finding | None:
    """Verify a stated stop distance against entry, stop and ATR (§7, §10).

    The regression this catches: a report claiming a stop at "2.5 ATR" when
    entry 557.00, stop 547.40 and ATR 9.408 give 1.02 ATR. The claim is off
    by a factor of 2.5, which matters because the ATR multiple is what the
    policy's minimum-buffer rule is measured against.

    A **wrong-side stop** is reported as a contradiction regardless of any
    stated distance: a LONG stop above the entry protects nothing.
    """
    entry_d, stop_d, atr_d = as_decimal(entry), as_decimal(stop), as_decimal(atr)
    if entry_d is None or stop_d is None or atr_d is None:
        if stated_atr_distance is not None:
            return Finding(
                kind=FindingKind.UNVERIFIED, code="STOP_DISTANCE_UNVERIFIED",
                message=("a stop distance was stated but entry, stop or ATR is "
                         "missing, so it cannot be verified"),
                values=(str(stated_atr_distance),), blocks=True,
            )
        return None

    side = direction.upper()
    wrong_side = ((side == "LONG" and stop_d >= entry_d)
                  or (side == "SHORT" and stop_d <= entry_d))
    if wrong_side:
        return Finding(
            kind=FindingKind.CONTRADICTION, code="STOP_WRONG_SIDE",
            message=(f"a {side} stop at {stop_d} on an entry at {entry_d} is on "
                     "the wrong side: it protects nothing"),
            values=(str(entry_d), str(stop_d)), blocks=True,
        )

    actual = atr_distance(entry_d, stop_d, atr_d, direction=side)
    if actual is None:
        return None
    stated = as_decimal(stated_atr_distance)
    if stated is None:
        return None
    if abs(actual - stated) > tolerance:
        return Finding(
            kind=FindingKind.CONTRADICTION,
            code="INVALID_STOP_ATR_DISTANCE",
            message=(f"the report states a {quantize(stated, RATIO_QUANTUM)} ATR "
                     f"stop but entry {entry_d}, stop {stop_d} and ATR {atr_d} "
                     f"give {quantize(actual, RATIO_QUANTUM)} ATR"),
            values=(str(stated), str(actual)), blocks=True,
        )
    return None


def rating_execution_alignment(strategic_rating: str | None,
                               execution_action: str | None,
                               authorized_orders: int = 0) -> Finding | None:
    """Check the strategic rating against the execution action (§10).

    ``OVERWEIGHT`` with ``WAIT`` is legitimate — a good company, wrong price
    — and is not a contradiction. What *is* one: an explicit avoidance or
    reduction rating alongside authorized orders, or orders without a rating
    that could justify them.
    """
    if execution_action is None:
        return None
    rating = (strategic_rating or "").upper()
    if authorized_orders > 0 and rating in {"UNDERWEIGHT", "AVOID", "REDUCE"}:
        return Finding(
            kind=FindingKind.CONTRADICTION,
            code="RATING_ORDER_CONFLICT",
            message=(f"{authorized_orders} order(s) authorized under a "
                     f"'{rating}' rating: a rating that says avoid cannot "
                     "carry an order"),
            values=(rating, execution_action), blocks=True,
        )
    if authorized_orders > 0 and rating not in {"OVERWEIGHT"}:
        return Finding(
            kind=FindingKind.INCONSISTENCY,
            code="RATING_ORDER_MISMATCH",
            message=(f"{authorized_orders} order(s) authorized under an "
                     f"'{rating or 'unstated'}' rating; only an overweight "
                     "rating justifies proposing an order"),
            values=(rating, execution_action), blocks=False,
        )
    return None


def check_stale_period(metric_period: str | None, reference_period: str | None,
                       metric_name: str) -> Finding | None:
    """Refuse a metric whose period differs from the period it is applied to.

    A P/B built on Q2 book value while the price and the discussion are Q3
    mixes two dates; the number looks normal and means nothing (§5: "Se il
    Q3 è già disponibile, non utilizzare silenziosamente il Q2").
    """
    if metric_period is None or reference_period is None:
        return None
    if metric_period == reference_period:
        return None
    return Finding(
        kind=FindingKind.CONTRADICTION,
        code="STALE_PERIOD_MIXING",
        message=(f"'{metric_name}' uses the period {metric_period} while the "
                 f"analysis is for {reference_period}: the figure mixes two "
                 "accounting periods"),
        values=(metric_period, reference_period), blocks=True,
    )


def check_share_class_mix(price_class: str | None, value_class: str | None,
                          metric_name: str) -> Finding | None:
    """Refuse a metric that divides a class-A figure by a class-B one.

    Berkshire's ratio is 1:1500, so a cross-class P/B is wrong by three
    orders of magnitude — and looks like a plausible multiple.
    """
    if not price_class or not value_class:
        return None
    if price_class.upper() == value_class.upper():
        return None
    return Finding(
        kind=FindingKind.CONTRADICTION,
        code="SHARE_CLASS_MIX",
        message=(f"'{metric_name}' compares a class-{price_class.upper()} figure "
                 f"with a class-{value_class.upper()} one without conversion"),
        values=(price_class, value_class), blocks=True,
    )


def check_definition_mix(left, right, metric_name: str = "metric") -> Finding | None:
    """Refuse a metric computed across two different definitions (§5).

    Case B of the regression: revenue of 74,322 (segment) against 105,647
    (consolidated). The growth rate across them is arithmetically perfect, so
    only a definition check can catch it.
    """
    if left is None or right is None:
        return None
    if left.definition is right.definition:
        return None
    if not left.is_labelled() and not right.is_labelled():
        return None
    return Finding(
        kind=FindingKind.CONTRADICTION,
        code="DEFINITION_MIX",
        message=(f"'{metric_name}' combines a {left.definition} figure with a "
                 f"{right.definition} one: these measure different things, so "
                 "any metric across them is not comparable"),
        values=(str(left.definition), str(right.definition)),
        blocks=True,
    )


def check_report_consistency(
    *,
    reports: dict[str, str] | None = None,
    computed_metrics: dict[str, Any] | None = None,
    metrics: list[MetricRecord] | None = None,
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
    left_identity: Any = None,
    right_identity: Any = None,
) -> ConsistencyReport:
    """Run every cross-report check and collect the diagnostic section.

    All inputs are optional; each check runs only when its inputs exist, and
    a check that cannot run adds no finding rather than a guess. The result
    is a report the caller can attach to the audit and print in the final
    document.
    """
    report = ConsistencyReport()

    if reports:
        report.claims = check_reports(reports, computed_metrics or {})
        # Every claim is reported, but only a contradiction blocks.
        #
        # A MISMATCH is the engine disproving a figure the report presents:
        # nothing downstream can be trusted, so the executable decision stops.
        # A NOT_CHECKABLE claim is a figure the engine has no value for — which
        # is not the same as a wrong figure. Treating it as blocking made every
        # run fail whenever no metric had been computed (the F6 defect the data
        # lineage audit found): the report is still worth producing, and what
        # must stop is the *order*, which happens because no usable metric
        # exists to certify the decision.
        for result in report.claims.results:
            contradicted = result.verdict.value == "MISMATCH"
            report.findings.append(Finding(
                kind=(FindingKind.CONTRADICTION
                      if contradicted else FindingKind.UNVERIFIED),
                code=("NUMERIC_CLAIM_MISMATCH" if contradicted
                      else f"NUMERIC_CLAIM_{result.verdict.value}"),
                message=(f"agent '{result.claim.agent}' stated "
                         f"'{result.claim.label}' = {result.claim.value}: "
                         f"{result.reason}") if result.reason else
                        f"agent '{result.claim.agent}' claim refused",
                agents=(result.claim.agent,),
                values=(str(result.claim.value),
                        result.record.display if result.record else ""),
                blocks=contradicted,
            ))

    report.findings.extend(cross_agent_numeric_consistency(reports or {}, extracted_claims))

    stop_finding = check_stop_consistency(
        entry, stop, atr, direction=direction,
        stated_atr_distance=stated_atr_distance,
    )
    if stop_finding is not None:
        report.findings.append(stop_finding)

    alignment = rating_execution_alignment(
        strategic_rating, execution_action, authorized_orders)
    if alignment is not None:
        report.findings.append(alignment)

    stale = check_stale_period(metric_period, reference_period, metric_name)
    if stale is not None:
        report.findings.append(stale)

    shared = check_share_class_mix(price_class, value_class, metric_name)
    if shared is not None:
        report.findings.append(shared)

    # §5: two figures with different definitions must not be combined. This
    # is the only check that can catch case B — the arithmetic of dividing
    # 105,647 by 74,322 is flawless.
    definition_finding = check_definition_mix(left_identity, right_identity,
                                              metric_name)
    if definition_finding is not None:
        report.findings.append(definition_finding)

    if metrics:
        report.metrics.extend(metrics)

    return report
