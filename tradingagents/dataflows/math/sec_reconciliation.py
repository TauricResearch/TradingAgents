"""SEC/XBRL semantic reconciliation (§4): a concept is not a number.

The 19:24 report presented Q3 revenue of 74,322 as the consolidated total.
It is a real, correctly-tagged figure — `RevenueFromContractWithCustomerExcludingAssessedTax`
— but it is a *subset* of what the filing also reports as
`Revenues` (105,647) for the same quarter, same unit, same entity.

Nothing in the arithmetic can catch that. The period matches, the unit
matches, the company matches, and 74,322 is a true number. The defect lives in
the concept: the report used the narrower accounting definition and called it
the consolidated one blot.

So this module checks what the numbers mean, in XBRL's own terms:

``concept``
    The tag itself. ``Revenues`` is the broad total; the
    ``RevenueFromContractWith...`` family measures only contract revenue.
``period``
    Both ``start`` and ``end``. A year-to-date figure and a quarter figure
    share an ``end`` but not a ``start``, which is how 301,130 and 105,647
    differ despite both being "Q3 2026".
``unit`` and ``frame``
    ``CY2026Q3`` states the calendar quarter explicitly; its absence means the
    figure is a duration the filer chose.
``form`` and ``accn``
    The filing it came from, so a reconciliation can point at a document.

A mismatch is reported as ``FINANCIAL_METRIC_DEFINITION_MISMATCH`` and blocks
before the Fundamentals Analyst sees the number (§4: "Questo controllo deve
avvenire prima del Fundamentals Analyst").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# The gate/audit code §4 requires for irreconcilable definitions.
FINANCIAL_METRIC_DEFINITION_MISMATCH = "FINANCIAL_METRIC_DEFINITION_MISMATCH"
SEC_CONCEPT_MISMATCH = "SEC_CONCEPT_MISMATCH"
SEC_PERIOD_SPAN_MISMATCH = "SEC_PERIOD_SPAN_MISMATCH"
SEC_METRIC_RECONCILED = "SEC_METRIC_RECONCILED"


class RevenueScope(StrEnum):
    """How broad a revenue concept is, in accounting terms.

    The ordering is the point: a value from a ``CONTRACT`` concept may not be
    presented as ``CONSOLIDATED``, because it is one component of it. The
    filer's own figures make the relationship visible — 105,647 is `Revenues`,
    74,322 is contract revenue, and the difference is the rest of the business.
    """

    CONSOLIDATED = "consolidated"      # Revenues, SalesRevenueNet
    CONTRACT = "contract"              # revenue from contracts with customers
    SEGMENT = "segment"                # a reportable segment's revenue
    COMPONENT = "component"            # interest, premiums, other income
    UNKNOWN = "unknown"


# XBRL concepts, classified by what they actually measure. Extend rather than
# guess: an unknown tag is `UNKNOWN`, and an `UNKNOWN` tag may not be
# presented as the consolidated total.
CONCEPT_SCOPES: dict[str, RevenueScope] = {
    "Revenues": RevenueScope.CONSOLIDATED,
    "SalesRevenueNet": RevenueScope.CONSOLIDATED,
    "RevenuesNetOfInterestExpense": RevenueScope.CONSOLIDATED,
    "RevenueFromContractWithCustomerExcludingAssessedTax": RevenueScope.CONTRACT,
    "RevenueFromContractWithCustomerIncludingAssessedTax": RevenueScope.CONTRACT,
    "SegmentReportingInformationRevenue": RevenueScope.SEGMENT,
    "RevenueNotFromContractWithCustomer": RevenueScope.COMPONENT,
    "InterestIncomeExpenseNet": RevenueScope.COMPONENT,
    "PremiumsEarnedNet": RevenueScope.COMPONENT,
}

# Scopes that may legitimately be called "the consolidated total".
_CONSOLIDATED_SCOPES = frozenset({RevenueScope.CONSOLIDATED})


@dataclass(frozen=True)
class SecFact:
    """One XBRL fact, with the metadata that decides its meaning.

    ``start`` matters as much as ``end``: a year-to-date figure and a quarter
    figure both end 2026-09-30 but begin six months apart, so comparing them
    without the start date is the DEF-002 hazard in a new disguise.
    """

    concept: str
    value: float
    unit: str
    end: str
    start: str | None = None
    fy: int | None = None
    fp: str | None = None
    form: str | None = None
    accn: str | None = None
    frame: str | None = None
    taxonomy: str = "us-gaap"

    @property
    def scope(self) -> RevenueScope:
        return CONCEPT_SCOPES.get(self.concept, RevenueScope.UNKNOWN)

    @property
    def is_duration(self) -> bool:
        """Whether the fact covers a span rather than an instant."""
        return self.start is not None

    def summary(self) -> dict:
        return {
            "concept": self.concept,
            "value": self.value,
            "unit": self.unit,
            "start": self.start,
            "end": self.end,
            "fy": self.fy,
            "fp": self.fp,
            "form": self.form,
            "accn": self.accn,
            "frame": self.frame,
            "scope": str(self.scope),
        }


@dataclass(frozen=True)
class ReconciliationFinding:
    """Why a reported figure may not be used as the metric it was called."""

    code: str
    message: str
    reported: SecFact | None = None
    expected: SecFact | None = None
    blocks: bool = True

    def summary(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "blocks": self.blocks,
            "reported": self.reported.summary() if self.reported else None,
            "expected": self.expected.summary() if self.expected else None,
        }


@dataclass
class RevenueReconciliation:
    """The verdict on one reported revenue figure."""

    reported_value: float | None
    resolved: SecFact | None = None
    findings: list[ReconciliationFinding] = field(default_factory=list)

    @property
    def blocks_decision(self) -> bool:
        return any(f.blocks for f in self.findings)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(f.code for f in self.findings))

    def summary(self) -> dict:
        return {
            "reported_value": self.reported_value,
            "status": ("BLOCKED" if self.blocks_decision
                       else ("OK" if self.resolved else None)),
            "resolved_concept": (
                self.resolved.summary() if self.resolved else None
            ),
            "findings": [f.summary() for f in self.findings],
        }


def sec_facts_from_companyfacts(payload: dict, concept: str,
                                unit: str = "USD") -> list[SecFact]:
    """Read every fact for one concept out of a SEC ``companyfacts`` payload.

    Returns an empty list when the concept or unit is absent, rather than
    raising: an unreported concept is a gap to report, not a crash.
    """
    try:
        rows = payload["facts"]["us-gaap"][concept]["units"][unit]
    except (KeyError, TypeError):
        return []
    facts: list[SecFact] = []
    for row in rows or []:
        try:
            value = float(row["val"])
        except (KeyError, TypeError, ValueError):
            continue
        end = str(row.get("end") or "")[:10]
        if not end:
            continue
        start = row.get("start")
        facts.append(SecFact(
            concept=concept,
            value=value,
            unit=unit,
            end=end,
            start=str(start)[:10] if start else None,
            fy=row.get("fy"),
            fp=row.get("fp"),
            form=row.get("form"),
            accn=row.get("accn"),
            frame=row.get("frame"),
        ))
    return facts


def _same_span(left: SecFact, right: SecFact) -> bool:
    """Whether two facts cover the same duration, not merely the same end."""
    return (left.end == right.end and (left.start or "") == (right.start or ""))


def _span_days(fact: SecFact) -> int:
    """How many calendar days a duration fact covers; 0 for an instant.

    Used to pick the counterpart whose span best matches: a year-to-date
    subset needs the year-to-date total, and both end on the same day, so only
    the span distinguishes them.
    """
    if not fact.start:
        return 0
    try:
        from datetime import date

        start = date.fromisoformat(fact.start)
        end = date.fromisoformat(fact.end)
        return (end - start).days
    except (ValueError, TypeError):
        return 0


def reconcile_revenue(
    reported_value: float | None,
    candidates: list[SecFact],
    *,
    claimed_as_consolidated: bool = True,
    tolerance_pct: float = 0.5,
) -> RevenueReconciliation:
    """Check a reported revenue figure against the filing's own concepts (§4).

    Three failures, in the order they matter:

    1. **No matching fact.** The value is not in the filing at all, so it is
       not certified. Blocks.
    2. **A narrower concept presented as the total.** This is the regression:
       74,322 is contract revenue, not `Revenues` of 105,647. Blocks with
       `FINANCIAL_METRIC_DEFINITION_MISMATCH`.
    3. **A broader concept than the claim allows.** Reporting 105,647 as
       "contract revenue" understates the definition in the other direction.
       Blocks for the same reason.

    A value that matches the consolidated concept is resolved and usable.
    """
    result = RevenueReconciliation(reported_value=reported_value)
    if reported_value is None:
        result.findings.append(ReconciliationFinding(
            code=FINANCIAL_METRIC_DEFINITION_MISMATCH,
            message="no revenue value was reported, so nothing can be reconciled",
        ))
        return result

    # The fact the reported figure actually corresponds to. Several concepts
    # can be within tolerance of the same number — 207,574 (2026 year-to-date)
    # and 207,771 (2022 annual) differ by 0.1% — so the *closest* match wins,
    # not the first one encountered. Taking the first would attribute a 2026
    # figure to a 2022 filing and reconcile against the wrong year.
    matched: SecFact | None = None
    best_delta = float("inf")
    for fact in candidates:
        if fact.value == 0:
            continue
        delta_pct = abs(fact.value - reported_value) / abs(fact.value) * 100.0
        if delta_pct <= tolerance_pct and delta_pct < best_delta:
            matched = fact
            best_delta = delta_pct

    if matched is None:
        result.findings.append(ReconciliationFinding(
            code=FINANCIAL_METRIC_DEFINITION_MISMATCH,
            message=(f"the reported revenue {reported_value:,.0f} does not match "
                     "any concept in the filing, so it is not certified"),
        ))
        return result

    if not claimed_as_consolidated:
        # The report said what it meant; a narrower figure is legitimate.
        result.resolved = matched
        result.findings.append(ReconciliationFinding(
            code=SEC_METRIC_RECONCILED,
            message=(f"reported as {matched.concept} ({matched.scope}), which is "
                     "what was claimed"),
            reported=matched, blocks=False,
        ))
        return result

    # Claimed as the consolidated total: the concept must actually be it.
    if matched.scope in _CONSOLIDATED_SCOPES:
        result.resolved = matched
        result.findings.append(ReconciliationFinding(
            code=SEC_METRIC_RECONCILED,
            message=f"{matched.concept} is the consolidated total",
            reported=matched, blocks=False,
        ))
        return result

    consolidated = None
    if candidates:
        same_span = [f for f in candidates
                     if f.scope in _CONSOLIDATED_SCOPES and _same_span(f, matched)]
        if same_span:
            # Same duration: the quarterly subset pairs with the quarterly total.
            consolidated = max(same_span, key=lambda f: f.end)
        else:
            # No total covers exactly the same duration. Choose the one whose
            # span best matches the reported fact's span — a 6-month subset
            # needs the 6-month total, not the 3-month one that happens to end
            # on the same day. Year-to-date comparisons depend on this.
            same_year = [f for f in candidates
                         if f.scope in _CONSOLIDATED_SCOPES
                         and f.fy is not None and f.fy == matched.fy]
            pool = same_year or [f for f in candidates
                                 if f.scope in _CONSOLIDATED_SCOPES
                                 and f.end <= matched.end]
            if pool:
                # Closest span wins, not the longest: a 272-day year-to-date
                # figure pairs with the 301,130 year-to-date total, not with a
                # 364-day annual total from another year.
                matched_span = _span_days(matched)
                consolidated = min(
                    pool,
                    key=lambda f: (abs(_span_days(f) - matched_span), f.end),
                )
    if consolidated is not None:
        result.findings.append(ReconciliationFinding(
            code=FINANCIAL_METRIC_DEFINITION_MISMATCH,
            message=(
                f"the report presents {matched.value:,.0f} as consolidated "
                f"revenue, but that is {matched.concept} ({matched.scope}); the "
                f"filing's consolidated total for the same period is "
                f"{consolidated.value:,.0f} from {consolidated.concept}"
            ),
            reported=matched, expected=consolidated,
        ))
        result.resolved = consolidated
        return result

    result.findings.append(ReconciliationFinding(
        code=SEC_CONCEPT_MISMATCH,
        message=(f"{matched.value:,.0f} is {matched.concept} ({matched.scope}), "
                 "not a consolidated total, and the filing reports no "
                 "consolidated figure for the same duration"),
        reported=matched,
    ))
    return result


def reconcile_reported_figure(concept: str, reported_value: float | None,
                              facts: list[SecFact], *,
                              cannot_be_called: RevenueScope
                              = RevenueScope.CONSOLIDATED) -> RevenueReconciliation:
    """Check a figure attributed to ``concept`` against the filing (§4).

    Catches the other half of the hazard: a report saying `Revenues` while
    quoting a number that belongs to a narrower tag. The concept named and the
    concept matched must agree, or the attribution is wrong.
    """
    result = reconcile_revenue(reported_value, facts,
                               claimed_as_consolidated=False)
    if result.resolved is None:
        return result
    if result.resolved.concept != concept:
        result.findings.append(ReconciliationFinding(
            code=SEC_CONCEPT_MISMATCH,
            message=(f"the report attributes {reported_value:,.0f} to {concept}, "
                     f"but it is {result.resolved.concept}"
                     f" ({result.resolved.scope})"),
            reported=result.resolved,
        ))
    return result


def quarters_are_comparable(left: SecFact, right: SecFact) -> tuple[bool, str]:
    """Whether two facts cover comparable spans, for a growth calculation.

    The 301,130 figure and the 105,647 figure both end 2026-09-30. One is
    year-to-date (starts 2026-01-01), the other the quarter (starts 2026-07-01).
    Comparing them yields a plausible percentage and means nothing, so the
    ``start`` is what decides, not the ``end``.
    """
    if not left.is_duration or not right.is_duration:
        return False, "one of the facts is an instant, not a period"
    if left.start != right.start:
        return False, (
            f"different spans: {left.concept} starts {left.start} and "
            f"{right.concept} starts {right.start}"
        )
    if left.unit != right.unit:
        return False, f"different units: {left.unit} vs {right.unit}"
    return True, ""
