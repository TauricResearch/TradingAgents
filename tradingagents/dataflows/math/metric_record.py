"""Traceable metric records (§4, §13).

Every derived number the engine produces is wrapped in a ``MetricRecord``
carrying its formula, its operands, its units, its period and the status of
both its source and its calculation. This is what makes the audit
reproducible and what lets the final report state which figures were
verified and which were refused.

Two statuses are deliberately separate, because they fail for different
reasons and blame different components:

``source_status``
    Whether the inputs are trustworthy — a value an agent typed is
    ``LLM_CLAIMED``, however plausible it looks; a vendor figure is
    ``VERIFIED`` only once it reconciled.
``calculation_status``
    Whether *this* engine could compute the metric from those inputs.

A metric is usable for a decision only when both are ``VERIFIED``. A
missing denominator is ``NOT_COMPUTABLE``, not zero. A refused P/B stays in
the record with the reason, so a report can show the rejected 1.35x next to
the computed 1.4801 instead of quietly dropping it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from tradingagents.dataflows.math.precision import (
    RATIO_QUANTUM,
    as_decimal,
    quantize,
)


class SourceStatus(StrEnum):
    """Where a number came from, and whether it can be trusted."""

    VERIFIED = "VERIFIED"            # primary source, reconciled
    VENDOR_REPORTED = "VENDOR_REPORTED"  # served by a provider, not reconciled
    LLM_CLAIMED = "LLM_CLAIMED"      # asserted by a model: never a fact
    ESTIMATE = "ESTIMATE"            # analyst estimate, distinct from actual
    FORECAST = "FORECAST"            # projection, not history
    SCENARIO = "SCENARIO"            # hypothetical assumption
    MISSING = "MISSING"              # absent, and not invented


class CalculationStatus(StrEnum):
    """Whether the engine could compute the metric, and whether it passed."""

    VERIFIED = "VERIFIED"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"     # inputs insufficient or invalid
    MISMATCH = "MISMATCH"                # computed value contradicts a claim
    REFUSED = "REFUSED"                  # inputs fail a consistency rule
    UNSUPPORTED = "UNSUPPORTED"           # a claim with nothing to check it against


# A metric may feed a decision only from this status pair.
_TRUSTED_SOURCES = frozenset({SourceStatus.VERIFIED})


@dataclass(frozen=True)
class MetricRecord:
    """One derived metric, with everything needed to reproduce it.

    ``value`` is a ``Decimal`` (exact) and ``display`` the rounded string the
    report shows; keeping both means the audit trail never depends on
    presentation rounding. ``llm_claimed_value`` and ``difference`` are filled
    when an agent asserted a figure — the record then documents not only the
    right answer but that the report's answer was wrong (§6: "non limitarti a
    ricalcolare il dato: registra che l'affermazione originale era errata").
    """

    metric: str
    value: Decimal | None
    unit: str
    formula_id: str
    operands: dict[str, str] = field(default_factory=dict)
    period_end: str | None = None
    source_status: SourceStatus = SourceStatus.VERIFIED
    calculation_status: CalculationStatus = CalculationStatus.VERIFIED
    llm_claimed_value: Decimal | None = None
    difference: Decimal | None = None
    tolerance: Decimal | None = None
    reason: str = ""
    affected_decisions: tuple[str, ...] = field(default_factory=tuple)
    quantum: Decimal = RATIO_QUANTUM

    @property
    def is_usable(self) -> bool:
        """Whether this metric may influence a decision.

        Requires a verified source *and* a verified calculation: a
        perfectly-computed metric from an unverified input is still not a
        fact, and a verified input this engine could not compute from
        produced no number at all.
        """
        return (self.source_status in _TRUSTED_SOURCES
                and self.calculation_status is CalculationStatus.VERIFIED
                and self.value is not None)

    @property
    def blocks_decision(self) -> bool:
        """Whether this metric's state must stop an *executable* decision.

        Blocks when the engine could compute a value and the report
        contradicts it (``MISMATCH``), or when the record was refused for an
        inconsistency (``REFUSED``) or had a claim with nothing to check it
        against (``UNSUPPORTED``).

        Does **not** block on ``NOT_COMPUTABLE``: that status means the inputs
        were absent, which is a gap to report, not a contradiction to stop. It
        still prevents the metric from being *used* — ``is_usable`` is false and
        ``Registry.value`` returns ``None`` — and a decision resting on no
        certified metric is blocked by ``attach_registry_status``, not here.
        Treating an absent input as a contradiction is what made every run fail
        in the F6 defect the data lineage audit found.
        """
        return self.calculation_status in (
            CalculationStatus.MISMATCH,
            CalculationStatus.REFUSED,
            CalculationStatus.UNSUPPORTED,
        )

    @property
    def display(self) -> str | None:
        """The rounded value as the report should print it."""
        if self.value is None:
            return None
        return str(quantize(self.value, self.quantum))

    def summary(self) -> dict:
        """The contract's §4 shape, plus the audit fields §13 requires."""
        return {
            "metric": self.metric,
            "value": self.display,
            "unit": self.unit,
            "formula_id": self.formula_id,
            "operands": dict(self.operands),
            "period_end": self.period_end,
            "source_status": str(self.source_status),
            "calculation_status": str(self.calculation_status),
            "llm_claimed_value": (
                str(quantize(self.llm_claimed_value, self.quantum))
                if self.llm_claimed_value is not None else None
            ),
            "difference": (
                str(quantize(self.difference, self.quantum))
                if self.difference is not None else None
            ),
            "tolerance": str(self.tolerance) if self.tolerance is not None else None,
            "reason": self.reason,
            "affected_decisions": list(self.affected_decisions),
        }


def metric(
    name: str,
    value: Any,
    *,
    unit: str = "multiple",
    formula_id: str,
    operands: dict[str, Any] | None = None,
    period_end: str | None = None,
    source_status: SourceStatus = SourceStatus.VERIFIED,
    calculation_status: CalculationStatus | None = None,
    llm_claimed_value: Any = None,
    tolerance: Any = None,
    reason: str = "",
    affected_decisions: tuple[str, ...] = (),
    quantum: Decimal = RATIO_QUANTUM,
) -> MetricRecord:
    """Build a ``MetricRecord`` from raw values, deriving status and delta.

    A ``None`` value becomes ``NOT_COMPUTABLE`` unless the caller says
    otherwise, and a claimed value that differs from the computed one beyond
    ``tolerance`` becomes ``MISMATCH`` — so callers cannot accidentally
    publish a contradicted figure as verified.
    """
    exact = as_decimal(value)
    claimed = as_decimal(llm_claimed_value)

    difference = None
    if exact is not None and claimed is not None:
        difference = exact - claimed

    status = calculation_status
    if status is None:
        if exact is None:
            status = CalculationStatus.NOT_COMPUTABLE
        elif (difference is not None and tolerance is not None
                and abs(difference) > as_decimal(tolerance)):
            status = CalculationStatus.MISMATCH
        else:
            status = CalculationStatus.VERIFIED

    return MetricRecord(
        metric=name,
        value=exact,
        unit=unit,
        formula_id=formula_id,
        operands={k: str(v) for k, v in (operands or {}).items()},
        period_end=period_end,
        source_status=source_status,
        calculation_status=status,
        llm_claimed_value=claimed,
        difference=difference,
        tolerance=as_decimal(tolerance),
        reason=reason,
        affected_decisions=affected_decisions,
        quantum=quantum,
    )
