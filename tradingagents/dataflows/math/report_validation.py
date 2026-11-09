"""Analyst report validation (§7): the constraint lives in code, not in a prompt.

Telling a model "do not calculate" is not an enforcement. This module reads
the report an analyst actually produced, extracts the figures it states, and
checks them against the run's certified metrics. What comes back is
structured — every claim, its verdict, and whether it blocks — so the graph
can attach it rather than hoping the prose was careful.

The honest limitation, stated here rather than hidden: extraction finds only
*labelled* figures (a percentage next to "SMA200", a P/B next to "P/B").
An unlabelled number is not verified, which is the fail-closed direction, but
it is also not *reported*. The contract's preference — structured agent
output instead of prose — is what would close that gap fully.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tradingagents.dataflows.math.claims import (
    ClaimResult,
    ClaimsReport,
    ClaimVerdict,
    check_claim,
    extract_claims,
)
from tradingagents.dataflows.math.registry import MetricRegistry


@dataclass
class ReportValidation:
    """The verdict on one analyst's report, ready to attach to the run."""

    agent: str
    claims: ClaimsReport = field(default_factory=ClaimsReport)
    uncertified: list[str] = field(default_factory=list)
    registry_present: bool = False

    @property
    def blocks_decision(self) -> bool:
        """A report contradicting a certified value must not authorize anything.

        Only a *contradiction* blocks — a figure the engine computed and the
        report got wrong. A figure with no certified counterpart does not
        block on its own: before any metric is registered, every labelled
        number would be unverifiable and every run would fail, including the
        valid path the contract requires to work. Such figures are reported as
        unverified so the audit shows them, and a consumer that *did* register
        the metric gets the contradiction.
        """
        from tradingagents.dataflows.math.claims import ClaimVerdict

        return any(r.verdict is ClaimVerdict.MISMATCH for r in self.claims.results)

    @property
    def codes(self) -> tuple[str, ...]:
        return self.claims.blocking_labels

    @property
    def is_validated(self) -> bool:
        """Whether any certification happened at all.

        ``False`` means the registry was empty, so nothing could be checked.
        Reported rather than implied: an unattempted check is not a pass.
        """
        return self.registry_present and bool(self.claims.results)

    def summary(self) -> dict:
        return {
            "agent": self.agent,
            "status": "BLOCKED" if self.blocks_decision else (
                "OK" if self.claims.results else None),
            "registry_present": self.registry_present,
            "is_validated": self.is_validated,
            "blocking_claims": list(self.codes),
            "uncertified_metrics": list(self.uncertified),
            "claims": [r.summary() for r in self.claims.results],
        }


def validate_analyst_report(
    report: str | None,
    *,
    agent: str,
    registry: MetricRegistry | None,
    critical_labels: tuple[str, ...] = (),
) -> ReportValidation:
    """Check an analyst's report against the run's certified metrics.

    ``critical_labels`` names the metrics whose presence in the report
    requires a certified value. A figure for one of them that the registry
    cannot supply is reported as uncertified *and* blocks, because that is
    precisely a model computing on its own.

    With no registry there is nothing to check against, and every claim is
    unverifiable. That is reported honestly rather than treated as a pass.
    """
    validation = ReportValidation(agent=agent)
    if not report:
        return validation

    available: dict[str, object] = {}
    if registry is not None:
        available = registry.verification_map()
    validation.registry_present = bool(available)

    for claim in extract_claims(report, agent=agent):
        if claim.label in available:
            validation.claims.results.append(
                check_claim(claim, available[claim.label],
                            formula_id=f"report.{claim.label}")
            )
            continue

        # No certified value exists for this label.
        result = ClaimResult(
            claim=claim,
            verdict=ClaimVerdict.NOT_CHECKABLE,
            reason=("the engine has no certified value for this metric, so the "
                    "report's figure is unverified"),
        )
        validation.claims.results.append(result)
        if claim.label in critical_labels:
            validation.uncertified.append(claim.label)

    return validation
