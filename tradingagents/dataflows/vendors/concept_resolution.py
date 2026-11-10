"""XBRL concept resolution (§2 of P2): what a tagged figure actually measures.

The data lineage audit found F1: Berkshire's Q3 2026 revenue was reported as
74,322 when the filing also states 105,647 for the same quarter. Both are true.
74,322 is `RevenueFromContractWithCustomerExcludingAssessedTax` — revenue from
contracts with customers, a *subset* — and 105,647 is `Revenues`, the
consolidated total. The extractor took whichever tag appeared first in its list
and the concept was lost, so nothing downstream could tell a component from the
whole.

This module keeps the concept. Every figure carries what it measures, and the
scopes are ordered so that "the consolidated total" means exactly one thing:

``CONSOLIDATED``
    The whole entity: `Revenues`, `SalesRevenueNet`.
``CONTRACT``
    Revenue from contracts with customers — a component, not the total.
``SEGMENT``
    One reportable segment's revenue.
``COMPONENT``
    Interest, premiums, other income: parts that do not add up to the top line.

Two rules follow, and both matter:

**A subset is never silently promoted.** Asking for consolidated revenue when
only a component is filed returns *missing*, not the component. Substituting one
for the other is the defect this module exists to prevent.

**Concepts are never summed.** `Revenues` and contract revenue overlap; adding
them double-counts. A reconciliation between them would need the components to
be disjoint and complete, which is an accounting judgement this layer cannot
make — so it reports what each tag says and leaves the addition to nobody.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RevenueScope(StrEnum):
    """What a revenue concept measures, in accounting terms."""

    CONSOLIDATED = "consolidated"
    CONTRACT = "contract"
    SEGMENT = "segment"
    COMPONENT = "component"
    UNKNOWN = "unknown"


# The classification the audit asks for, per XBRL tag. Extend rather than guess:
# an unrecognised tag is UNKNOWN, and an UNKNOWN tag may not be presented as the
# consolidated total.
CONCEPT_SCOPES: dict[str, RevenueScope] = {
    # The whole entity's top line.
    "Revenues": RevenueScope.CONSOLIDATED,
    "SalesRevenueNet": RevenueScope.CONSOLIDATED,
    "RevenuesNetOfInterestExpense": RevenueScope.CONSOLIDATED,
    "RevenueFromContractWithCustomerIncludingAssessedTax": RevenueScope.CONTRACT,
    "RevenueFromContractWithCustomerExcludingAssessedTax": RevenueScope.CONTRACT,
    "SegmentReportingInformationRevenue": RevenueScope.SEGMENT,
    "RevenueNotFromContractWithCustomer": RevenueScope.COMPONENT,
    "InterestIncomeExpenseNet": RevenueScope.COMPONENT,
    "InterestAndDividendIncomeOperating": RevenueScope.COMPONENT,
    "PremiumsEarnedNet": RevenueScope.COMPONENT,
    "NoninterestIncome": RevenueScope.COMPONENT,
}

# Preference *within* a scope. `Revenues` is the plainest consolidated tag, so it
# wins over a variant when a filer reports both; `SalesRevenueNet` is the older
# spelling of the same thing. Ordering inside a scope is a rename question, not
# a meaning question — unlike the cross-scope ordering that caused F1.
_SCOPE_PREFERENCE: dict[str, tuple[int, ...]] = {
    "Revenues": (0,),
    "SalesRevenueNet": (1,),
    "RevenuesNetOfInterestExpense": (2,),
    "RevenueFromContractWithCustomerExcludingAssessedTax": (0,),
    "RevenueFromContractWithCustomerIncludingAssessedTax": (1,),
}


@dataclass(frozen=True)
class TagProvenance:
    """Everything needed to say where a figure came from and what it means.

    The audit asked for concept, definition, accession, period, unit, dimensions
    and consolidation perimeter. All of them travel with the value now, so a
    consumer can reject a figure on the grounds of what it measures without
    re-reading the filing.
    """

    concept: str
    scope: RevenueScope
    accession: str | None = None
    form: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    unit: str = "USD"
    dimensions: tuple[tuple[str, str], ...] = ()
    retrieved_at: str | None = None

    @property
    def is_consolidated(self) -> bool:
        """Whether this concept is the whole entity's figure.

        The one question that matters for the revenue row: a subset must never
        answer yes.
        """
        return self.scope is RevenueScope.CONSOLIDATED

    @property
    def is_dimensioned(self) -> bool:
        """Whether the fact carries an axis.

        A dimensioned fact is a slice — a segment, a product line — even when
        its tag is a consolidated one. The scope alone is not enough, so this is
        reported separately rather than folded into the classification.
        """
        return bool(self.dimensions)

    def summary(self) -> dict:
        return {
            "concept": self.concept,
            "definition": str(self.scope),
            "accession": self.accession,
            "form": self.form,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "unit": self.unit,
            "dimensions": [{"axis": a, "member": m} for a, m in self.dimensions],
            "consolidation_perimeter": (
                "consolidated" if self.is_consolidated
                and not self.is_dimensioned else str(self.scope)
            ),
            "is_consolidated": self.is_consolidated,
            "is_dimensioned": self.is_dimensioned,
            "retrieved_at": self.retrieved_at,
        }


def scope_of(concept: str) -> RevenueScope:
    """What a tag measures, or UNKNOWN when the taxonomy is unfamiliar."""
    return CONCEPT_SCOPES.get(concept, RevenueScope.UNKNOWN)


def preference_key(concept: str) -> tuple[int, int]:
    """Sort key: consolidated first, then the plainest spelling within a scope.

    Deliberately *not* a global tag order. F1 happened because a single list
    interleaved concepts of different scope; this key separates the two
    questions — meaning first, spelling second.
    """
    scope = scope_of(concept)
    scope_rank = {
        RevenueScope.CONSOLIDATED: 0,
        RevenueScope.CONTRACT: 1,
        RevenueScope.SEGMENT: 2,
        RevenueScope.COMPONENT: 3,
        RevenueScope.UNKNOWN: 4,
    }[scope]
    spelling = _SCOPE_PREFERENCE.get(concept, (99,))[0]
    return (scope_rank, spelling)


def ordered_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    """Order candidate tags by meaning, then by spelling.

    A filer that renamed a line keeps working — the tags still cover the
    history — while a narrower concept can no longer outrank the total.
    """
    return tuple(sorted(tags, key=preference_key))


@dataclass(frozen=True)
class ScopeSelection:
    """The figure chosen for a scope, and what was passed over.

    ``value is None`` with ``rejected`` populated is the honest outcome when a
    filer reports only a subset: the audit's requirement is to return missing
    rather than the subset.
    """

    scope: RevenueScope
    value: float | None
    provenance: TagProvenance | None
    rejected: tuple[TagProvenance, ...] = ()

    @property
    def available(self) -> bool:
        return self.value is not None and self.provenance is not None

    def summary(self) -> dict:
        return {
            "requested_scope": str(self.scope),
            "value": self.value,
            "available": self.available,
            "selected": (self.provenance.summary()
                         if self.provenance is not None else None),
            "rejected": [p.summary() for p in self.rejected],
        }


def select_by_scope(candidates: list[tuple[float, TagProvenance]],
                    scope: RevenueScope) -> ScopeSelection:
    """Choose the figure for ``scope`` from the facts a filer reports.

    Only an exact scope match qualifies. A consolidated request against a filer
    that reports contract revenue alone returns missing, with the rejected
    candidates listed so a caller can explain *why* rather than showing a blank.

    A dimensioned fact is rejected for a headline request: `Revenues` for a
    single segment is still a slice, whatever its tag says.
    """
    matching = [(v, p) for v, p in candidates
                if p.scope is scope and not p.is_dimensioned]
    rejected = tuple(p for _, p in candidates
                     if p.scope is not scope or p.is_dimensioned)
    if not matching:
        return ScopeSelection(scope=scope, value=None, provenance=None,
                              rejected=rejected)
    matching.sort(key=lambda pair: preference_key(pair[1].concept))
    value, provenance = matching[0]
    return ScopeSelection(scope=scope, value=value, provenance=provenance,
                          rejected=rejected)
