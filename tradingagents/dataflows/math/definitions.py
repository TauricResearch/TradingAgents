"""Metric definition reconciliation (§5): same number is not same meaning.

The 2026-11-09 report presented Q3 revenue of 74,322 against a consolidated
total of 105,647. Both are real figures; they are not the same metric. Any
growth rate computed across them is arithmetically flawless and financially
meaningless — which is why the arithmetic validator cannot catch it. Only a
comparison of *definitions* can.

This module answers one question: may two figures be combined? It refuses
when their definitions differ, and it says which dimension differs, so a
report can explain the refusal instead of silently choosing one.

The dimensions checked are the ones that actually change a number's meaning:

``definition``
    Consolidated vs segment vs adjusted. Blending these is case B.
``period``
    Q3 vs Q2, or a quarter against a TTM figure.
``basis``
    GAAP vs adjusted vs operating. Blending these is case C's cousin.
``currency`` and ``unit``
    Comparing a million-dollar figure to a base-dollar one without
    conversion is a 1,000x error that looks normal.
``share_count_basis``
    End-of-period vs weighted average. Choosing wrongly is case C exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class DefinitionKind(StrEnum):
    """What a revenue or earnings figure actually measures."""

    CONSOLIDATED = "consolidated"
    SEGMENT = "segment"
    ADJUSTED = "adjusted"
    OPERATING = "operating"
    GAAP = "gaap"
    UNKNOWN = "unknown"


class ShareCountBasis(StrEnum):
    """Which share count a per-share figure was divided by."""

    WEIGHTED_AVERAGE = "weighted_average"   # the GAAP EPS denominator
    PERIOD_END = "period_end"
    DILUTED = "diluted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MetricIdentity:
    """Everything that must agree before two figures may be combined.

    A default-constructed identity is ``UNKNOWN`` on every dimension, which
    the reconciler treats as "cannot confirm" rather than "matches": two
    unlabelled figures are not thereby compatible.
    """

    definition: DefinitionKind = DefinitionKind.UNKNOWN
    period: str | None = None
    basis: str | None = None
    currency: str | None = None
    unit: str = "base"
    share_count_basis: ShareCountBasis = ShareCountBasis.UNKNOWN

    def is_labelled(self) -> bool:
        """Whether this identity states enough to be compared at all."""
        return self.definition is not DefinitionKind.UNKNOWN


def period_granularity(period: str | None) -> str | None:
    """The *kind* of period a label names: ``quarter``, ``year``, ``ttm``.

    Two quarters are comparable even when they differ — that is what YoY and
    QoQ growth are. A quarter against a TTM figure is not, and no amount of
    arithmetic fixes it. Splitting the label this way is what lets the
    reconciler allow a legitimate YoY comparison while refusing a blend of
    unlike spans.
    """
    if not period:
        return None
    text = str(period).strip().upper()
    if "TTM" in text or "LTM" in text or "TRAILING" in text:
        return "ttm"
    # A quarter label: 2026-Q3, Q3 2026, 2026Q3.
    if "-Q" in text or "Q" in text.replace("-", ""):
        for token in text.replace("-", " ").split():
            if token.startswith("Q") and token[1:].isdigit():
                return "quarter"
        if re.search(r"\d{4}Q\d", text):
            return "quarter"
    # A bare year, or a fiscal-year label such as FY2026.
    if re.fullmatch(r"(FY)?\d{4}", text):
        return "year"
    return "other"


@dataclass(frozen=True)
class DefinitionConflict:
    """Why two figures may not be combined, and what to do instead."""

    code: str
    message: str
    dimension: str

    def summary(self) -> dict:
        return {"code": self.code, "message": self.message,
                "dimension": self.dimension}


@dataclass(frozen=True)
class ReconciledPair:
    """The verdict on two figures, plus what a caller may do with them."""

    compatible: bool
    conflicts: tuple[DefinitionConflict, ...] = ()

    @property
    def blocks_decision(self) -> bool:
        """An incompatible pair must not feed a computed metric.

        This is the guard case B needs: the growth rate across 105,647 and
        74,322 is well-formed, so the block cannot come from the arithmetic.
        """
        return not self.compatible

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(c.code for c in self.conflicts)

    def summary(self) -> dict:
        return {
            "compatible": self.compatible,
            "blocks_decision": self.blocks_decision,
            "conflicts": [c.summary() for c in self.conflicts],
        }


def reconcile_definitions(left: MetricIdentity,
                          right: MetricIdentity) -> ReconciledPair:
    """Decide whether two figures may be combined into one metric.

    Every differing dimension is reported, not just the first, so the caller
    can show all the reasons rather than fixing one and hitting the next.

    An unlabelled identity on either side is a conflict: the reconciler
    cannot confirm compatibility, and assuming it would be exactly the silent
    blend this module exists to prevent.
    """
    conflicts: list[DefinitionConflict] = []

    if not left.is_labelled() or not right.is_labelled():
        conflicts.append(DefinitionConflict(
            code="DEFINITION_UNLABELLED",
            message=("at least one figure does not state what it measures "
                     "(consolidated, segment, adjusted...), so they cannot be "
                     "compared safely"),
            dimension="definition",
        ))
        return ReconciledPair(compatible=False, conflicts=tuple(conflicts))

    if left.definition is not right.definition:
        conflicts.append(DefinitionConflict(
            code="DEFINITION_MISMATCH",
            message=(f"one figure is {left.definition} and the other is "
                     f"{right.definition}: a metric computed across them "
                     "would mix two different measures"),
            dimension="definition",
        ))

    if left.period and right.period and left.period != right.period:
        # Differing labels are fine when they name the same *kind* of span:
        # Q3 2026 against Q3 2025 is a YoY comparison, which is the whole
        # point of having periods. A quarter against a TTM figure is not.
        left_span = period_granularity(left.period)
        right_span = period_granularity(right.period)
        if left_span is None or right_span is None or left_span != right_span:
            conflicts.append(DefinitionConflict(
                code="PERIOD_MISMATCH",
                message=(f"the figures cover incomparable spans "
                         f"({left.period} is {left_span}, {right.period} is "
                         f"{right_span})"),
                dimension="period",
            ))

    if left.basis and right.basis and left.basis.lower() != right.basis.lower():
        conflicts.append(DefinitionConflict(
            code="BASIS_MISMATCH",
            message=(f"one figure is on a {left.basis} basis and the other on "
                     f"{right.basis}: GAAP, adjusted and operating are "
                     "different metrics"),
            dimension="basis",
        ))

    if left.currency and right.currency and left.currency.upper() != right.currency.upper():
        conflicts.append(DefinitionConflict(
            code="CURRENCY_MISMATCH",
            message=(f"different currencies ({left.currency} vs "
                     f"{right.currency})"),
            dimension="currency",
        ))

    # Units are a scale, so they are *convertible* — but only when both are
    # stated. An unstated unit is not base units by default.
    if left.unit and right.unit and left.unit.lower() != right.unit.lower():
        conflicts.append(DefinitionConflict(
            code="UNIT_SCALE_DIFFERS",
            message=(f"the figures are reported in different units "
                     f"({left.unit} vs {right.unit}): convert to a common "
                     "scale before combining them"),
            dimension="unit",
        ))

    if (left.share_count_basis is not ShareCountBasis.UNKNOWN
            and right.share_count_basis is not ShareCountBasis.UNKNOWN
            and left.share_count_basis is not right.share_count_basis):
        conflicts.append(DefinitionConflict(
            code="SHARE_BASIS_MISMATCH",
            message=(f"one figure uses {left.share_count_basis} shares and the "
                     f"other {right.share_count_basis}: a per-share metric "
                     "across them is not comparable"),
            dimension="share_count_basis",
        ))

    return ReconciledPair(compatible=not conflicts, conflicts=tuple(conflicts))


def requires_definition_check(left: MetricIdentity,
                              right: MetricIdentity) -> bool:
    """Whether combining these two figures needs the §5 guard at all.

    Two figures that both state a definition are compared; two that state
    none are refused by ``reconcile_definitions``. This predicate exists so a
    caller can report "not checked" honestly rather than implying a pass.
    """
    return left.is_labelled() or right.is_labelled()
