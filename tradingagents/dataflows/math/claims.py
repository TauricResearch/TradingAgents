"""Numeric claims validator (§9): never trust a number because a model said it.

Agents write prose containing figures — "about 9.5% above the 50-day", "P/B
of 1.35x", "stop at 2.5 ATR". Some are rounding of a real computation, some
are estimates, and some are simply wrong. This module classifies a claim and
decides whether it may reach a decision.

The classification the task requires is explicit:

``COMPUTED``
    The engine has a verified value for this metric. The claim is compared.
``OBSERVED``
    A figure read off a source (a close price). Checkable when the source
    value is supplied.
``ESTIMATE`` / ``FORECAST`` / ``SCENARIO``
    The agent's own projection. Not checked against reality, and never
    promoted to a fact.
``UNSUPPORTED``
    Nothing to check it against. It cannot authorize an order.

The extractor is deliberately **not** the security boundary. The task says
it plainly: "Non basare la sicurezza esclusivamente sull'estrazione di
numeri da testo libero tramite regex." Regex here only *finds* claims so
they can be reported; what blocks execution is the structured check in
``check_claim`` against an engine-computed metric. A number that regex
misses is not thereby trusted — it simply never became a verified fact,
which is the fail-closed default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from tradingagents.dataflows.math.metric_record import (
    CalculationStatus,
    MetricRecord,
    SourceStatus,
    metric,
)
from tradingagents.dataflows.math.precision import (
    PERCENT_QUANTUM,
    RATIO_QUANTUM,
    as_decimal,
    quantize,
)


class ClaimKind(StrEnum):
    """What kind of numeric statement an agent made."""

    COMPUTED = "COMPUTED"          # a derived metric the engine owns
    OBSERVED = "OBSERVED"          # read from a source
    ESTIMATE = "ESTIMATE"          # analyst estimate
    FORECAST = "FORECAST"          # projection
    SCENARIO = "SCENARIO"          # hypothetical
    UNSUPPORTED = "UNSUPPORTED"    # nothing to check against


class ClaimVerdict(StrEnum):
    """The outcome of checking a claim."""

    MATCHES = "MATCHES"
    MISMATCH = "MISMATCH"
    NOT_CHECKABLE = "NOT_CHECKABLE"
    ACCEPTED_NON_FACT = "ACCEPTED_NON_FACT"  # estimate/forecast: allowed, not a fact


# Default tolerance for a stated percentage, in percentage points: a report
# may round to one decimal, not be a different number.
PCT_TOLERANCE = Decimal("0.1")
# Default tolerance for a multiple (1.35 vs 1.4801 is far beyond).
MULTIPLE_TOLERANCE = Decimal("0.02")


@dataclass(frozen=True)
class NumericClaim:
    """One number an agent asserted, with where it came from."""

    claim_id: str
    label: str
    value: Decimal | None
    unit: str
    agent: str
    kind: ClaimKind
    source_text: str = ""

    def summary(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "label": self.label,
            "value": str(self.value) if self.value is not None else None,
            "unit": self.unit,
            "agent": self.agent,
            "kind": str(self.kind),
            "source_text": self.source_text[:200],
        }


@dataclass(frozen=True)
class ClaimResult:
    """A claim, the engine's verdict, and why."""

    claim: NumericClaim
    verdict: ClaimVerdict
    record: MetricRecord | None = None
    reason: str = ""

    @property
    def blocks(self) -> bool:
        """Only a contradicted *fact* blocks.

        A ``MISMATCH`` on a computed metric is a report asserting something
        the engine disproves — it blocks. ``NOT_CHECKABLE`` also blocks when
        the metric is critical: an unverifiable number must not authorize an
        order (§9). Estimates and forecasts are explicitly allowed through
        as non-facts so the agents can still reason about scenarios.
        """
        if self.verdict is ClaimVerdict.MISMATCH:
            return True
        if self.verdict is ClaimVerdict.NOT_CHECKABLE:
            return self.claim.kind in (ClaimKind.COMPUTED, ClaimKind.OBSERVED)
        return False

    def summary(self) -> dict:
        payload = self.claim.summary()
        payload["verdict"] = str(self.verdict)
        payload["blocks"] = self.blocks
        payload["reason"] = self.reason
        if self.record is not None:
            payload["computed_value"] = self.record.display
            payload["formula_id"] = self.record.formula_id
        return payload


def check_claim(claim: NumericClaim, computed: Any, *,
                tolerance: Any | None = None,
                formula_id: str = "unknown",
                period_end: str | None = None,
                affected_decisions: tuple[str, ...] = ()) -> ClaimResult:
    """Compare a claim against the engine's value for the same metric.

    ``computed`` is the engine's own result — never another agent's text.
    When it is ``None`` the claim is ``NOT_CHECKABLE``: there is no verified
    value to compare against, and an unverifiable critical claim must not
    pass as a fact.

    ``tolerance`` defaults by unit: percentage points for percentages,
    absolute multiple difference for ratios, so a caller cannot loosen one
    kind of check by forgetting a parameter.
    """
    computed_d = as_decimal(computed)
    # A claim may arrive as a float from a tool argument or from prose; convert
    # it once so the comparison is Decimal against Decimal. Mixing the two
    # raises TypeError, which surfaced only when a tool built a claim directly.
    claimed_d = as_decimal(claim.value)
    is_pct = claim.unit in ("percent", "percentage_points")
    tol = (as_decimal(tolerance) if tolerance is not None
           else (PCT_TOLERANCE if is_pct else MULTIPLE_TOLERANCE))
    quantum = PERCENT_QUANTUM if is_pct else RATIO_QUANTUM

    if computed_d is None or claimed_d is None:
        return ClaimResult(
            claim=claim, verdict=ClaimVerdict.NOT_CHECKABLE,
            record=metric(
                claim.label, computed_d, unit=claim.unit, formula_id=formula_id,
                period_end=period_end, llm_claimed_value=claimed_d,
                source_status=SourceStatus.LLM_CLAIMED,
                calculation_status=CalculationStatus.UNSUPPORTED,
                reason="no computed value to check the claim against",
                affected_decisions=affected_decisions, quantum=quantum,
            ),
            reason="the claim cannot be verified: no engine value for this metric",
        )

    difference = computed_d - claimed_d
    within = abs(difference) <= tol
    record = metric(
        claim.label, computed_d, unit=claim.unit, formula_id=formula_id,
        period_end=period_end, llm_claimed_value=claimed_d,
        tolerance=tol, source_status=SourceStatus.LLM_CLAIMED,
        calculation_status=(CalculationStatus.VERIFIED if within
                            else CalculationStatus.MISMATCH),
        reason=("" if within else
                f"the agent stated {quantize(claimed_d, quantum)}, the engine "
                f"computes {quantize(computed_d, quantum)} "
                f"(off by {quantize(difference, quantum)}, tolerance {tol})"),
        affected_decisions=affected_decisions, quantum=quantum,
    )
    return ClaimResult(
        claim=claim,
        verdict=ClaimVerdict.MATCHES if within else ClaimVerdict.MISMATCH,
        record=record,
        reason=record.reason,
    )


def accept_non_fact(claim: NumericClaim, *, reason: str = "") -> ClaimResult:
    """Accept an estimate, forecast or scenario **as a non-fact**.

    The distinction is the whole point of §9: an analyst may say "I expect
    8% growth", and that must not be treated as a verified 8%. The claim is
    allowed to inform reasoning and is recorded as what it is, so nothing
    downstream can mistake it for an observed value.
    """
    if claim.kind in (ClaimKind.COMPUTED, ClaimKind.OBSERVED):
        raise ValueError(
            f"{claim.kind} claims must be checked, not accepted as non-facts")
    return ClaimResult(
        claim=claim, verdict=ClaimVerdict.ACCEPTED_NON_FACT,
        reason=reason or f"{claim.kind} claim accepted as a non-fact, not verified",
    )


# --- Extraction: finding claims so they can be *reported* -------------------
#
# These patterns locate labelled figures in prose. They are a reporting aid,
# not a trust boundary: a claim they miss is simply never verified, which is
# the safe direction. Each requires an explicit label, because a bare number
# in a sentence has no metric identity to check it against.

# Each entry is (label, pattern, unit, value_group). ``value_group`` names the
# capture holding the claimed figure, because a pattern may also capture a
# window ("SMA200") whose number is not the claim: taking the last group
# turned "4.5% above SMA200" into a claim of 200%.
_CLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str], str, int], ...] = (
    # Reports write this both ways round — "11.3% below the high" and
    # "-2.63% from the high" — so both orders are matched.
    ("distance_from_high",
     re.compile(
         r"(?:([-+]?\d+(?:\.\d+)?)\s*%\s+(?:below|above|from|off)\s+(?:the\s+)?"
         r"(?:52[- ]week\s+)?high)"
         r"|(?:(?:from|below|off)\s+(?:the\s+)?(?:52[- ]week\s+)?high[^.]{0,20}?"
         r"([-+]?\d+(?:\.\d+)?)\s*%)",
         re.IGNORECASE), "percent", -1),
    ("distance_from_sma",
     re.compile(r"([-+]?\d+(?:\.\d+)?)\s*%\s+(?:above|below)\s+(?:the\s+)?(?:SMA|EMA)\s*\d*",
                re.IGNORECASE), "percent", 1),
    ("price_to_book",
     re.compile(r"P/?B[^.\d]{0,20}(\d+(?:\.\d+)?)\s*x?", re.IGNORECASE), "multiple", 1),
    ("stop_atr",
     re.compile(r"(\d+(?:\.\d+)?)\s*(?:x\s*)?ATR[s]?\b", re.IGNORECASE), "multiple", 1),
    ("risk_reward",
     re.compile(r"(?:R:?R|risk[/-]reward)[^.\d]{0,12}(\d+(?:\.\d+)?)", re.IGNORECASE),
     "multiple", 1),
    # EPS growth or contraction, in the phrasings a report actually uses:
    # "EPS contracts 37%", "EPS growth of -37%", "a 37% decline in EPS".
    # Case A of the 2026-11-09 19:24 report is exactly this claim.
    ("eps_change",
     re.compile(
         r"\bEPS\b[^.\d%]{0,40}?([-+]?\d+(?:\.\d+)?)\s*%"
         r"|([-+]?\d+(?:\.\d+)?)\s*%\s+(?:decline|contraction|drop|growth|increase|"
         r"decrease)\s+in\s+\bEPS\b",
         re.IGNORECASE), "percent", -1),
    # VIX change, the same shape: "VIX rose 58%", "VIX at 28.18 from 16.61
    # (+58%)".
    ("vix_change",
     re.compile(
         r"\bVIX\b[^.\d%]{0,40}?([-+]?\d+(?:\.\d+)?)\s*%"
         r"|\(?([-+]?\d+(?:\.\d+)?)\s*%\)?[^.]{0,30}?\bVIX\b",
         re.IGNORECASE), "percent", -1),
)


def extract_claims(text: str | None, agent: str = "unknown") -> list[NumericClaim]:
    """Locate labelled numeric claims in an agent's prose.

    Returns claims with ``kind=COMPUTED`` — they *purport* to be derived
    metrics. Whether each is true is decided by ``check_claim`` against the
    engine, never here. Numbers without a recognised label are not returned,
    and that is intentional: they carry no metric identity, so they can be
    neither verified nor used.
    """
    if not text:
        return []
    found: list[NumericClaim] = []
    seen: set[tuple[str, str]] = set()
    for label, pattern, unit, value_group in _CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            if value_group == -1:
                # Alternation pattern: whichever branch captured wins.
                raw = next((g for g in match.groups() if g is not None), None)
                value = as_decimal(raw)
            else:
                value = as_decimal(match.group(value_group))
            if value is None:
                continue
            key = (label, str(value))
            if key in seen:
                continue
            seen.add(key)
            start = max(0, match.start() - 40)
            found.append(NumericClaim(
                claim_id=f"{label}:{len(found)}",
                label=label, value=value, unit=unit, agent=agent,
                kind=ClaimKind.COMPUTED,
                source_text=text[start:match.end()].strip(),
            ))
    return found


@dataclass
class ClaimsReport:
    """Every claim found in a run, with the blocking subset highlighted."""

    results: list[ClaimResult] = field(default_factory=list)

    @property
    def blocking(self) -> list[ClaimResult]:
        return [r for r in self.results if r.blocks]

    @property
    def blocks_decision(self) -> bool:
        return bool(self.blocking)

    @property
    def blocking_labels(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(r.claim.label for r in self.blocking))

    def summary(self) -> dict:
        return {
            "claims": [r.summary() for r in self.results],
            "blocking_claims": list(self.blocking_labels),
            "status": "BLOCKED" if self.blocks_decision else (
                "OK" if self.results else None),
        }


def check_reports(reports: dict[str, str], computed: dict[str, Any], *,
                  tolerances: dict[str, Any] | None = None
                  ) -> ClaimsReport:
    """Check every claim across several agents' reports against the engine.

    ``computed`` maps a claim label to the engine's verified value for it.
    A label absent from ``computed`` yields ``NOT_CHECKABLE`` — the honest
    outcome when the engine has not computed that metric, and the reason a
    report cannot certify a figure nobody verified.
    """
    report = ClaimsReport()
    tolerances = tolerances or {}
    for agent, text in reports.items():
        for claim in extract_claims(text, agent=agent):
            if claim.label not in computed:
                report.results.append(ClaimResult(
                    claim=claim, verdict=ClaimVerdict.NOT_CHECKABLE,
                    reason=(f"the engine has no computed value for "
                            f"'{claim.label}' to verify this claim against"),
                ))
                continue
            report.results.append(check_claim(
                claim, computed[claim.label],
                tolerance=tolerances.get(claim.label),
                formula_id=f"claims.{claim.label}",
            ))
    return report
