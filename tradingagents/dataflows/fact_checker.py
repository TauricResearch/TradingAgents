"""Independent Fact Checker (Phase 5, contract section 6).

An obligatory step between analysis and synthesis: every material claim an
analyst or the Portfolio Manager makes is classified, checked against the
run's verified facts, and either upheld or refuted with a machine-readable
reason. A refuted *blocking* claim imposes a BLOCK on the decision — the
Fact Checker can contradict anyone, including the Portfolio Manager.

The checker introduces no data of its own: it reasons only over the claims
presented and the provenance registry's facts (Phase 1). Every verdict is
auditable — claim, classification, supporting fact ids, status, reason.

Classifications follow the contract's minimum set. ``REFUTED`` is a status,
not a classification: a claim that was checked and contradicted keeps its
original classification and gains the refuted status plus a reason code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from tradingagents.dataflows.causal_guard import NOT_YET_OBSERVABLE
from tradingagents.dataflows.provenance import ProvenanceRegistry


class ClaimClassification(StrEnum):
    """What kind of statement the claim is (contract's minimum set)."""

    FACT = "FACT"
    DERIVED_CALCULATION = "DERIVED_CALCULATION"
    CAUSAL_INFERENCE = "CAUSAL_INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    FORECAST = "FORECAST"
    UNSUPPORTED = "UNSUPPORTED"


class ClaimStatus(StrEnum):
    """The check's outcome for a claim."""

    SUPPORTED = "SUPPORTED"
    UNVERIFIED = "UNVERIFIED"
    REFUTED = "REFUTED"


class ReasonCode(StrEnum):
    """Machine-readable reasons, stable for reports and the audit trail."""

    OK = "OK"
    NO_SUPPORTING_FACTS = "NO_SUPPORTING_FACTS"
    SUPPORTING_FACTS_UNVERIFIED = "SUPPORTING_FACTS_UNVERIFIED"
    SUPPORTING_FACTS_QUARANTINED = "SUPPORTING_FACTS_QUARANTINED"
    EVENT_AFTER_LAST_MARKET_SESSION = "EVENT_AFTER_LAST_MARKET_SESSION"
    POST_EVENT_PRICES_UNAVAILABLE = "POST_EVENT_PRICES_UNAVAILABLE"
    CONTRADICTED_BY_REGISTRY = "CONTRADICTED_BY_REGISTRY"
    HYPOTHESIS_STATED_AS_FACT = "HYPOTHESIS_STATED_AS_FACT"


@dataclass(frozen=True)
class Claim:
    """One material claim as presented by an analyst or manager."""

    claim_id: str
    statement: str
    classification: ClaimClassification
    supporting_fact_ids: tuple[str, ...] = ()
    blocking: bool = False


@dataclass(frozen=True)
class ClaimVerdict:
    """The Fact Checker's verdict on one claim."""

    claim_id: str
    statement: str
    classification: ClaimClassification
    supporting_fact_ids: tuple[str, ...]
    status: ClaimStatus
    reason_code: ReasonCode
    blocking: bool

    @property
    def blocks_decision(self) -> bool:
        """Only a refuted *blocking* claim stops the decision (contract §6)."""
        return self.blocking and self.status is ClaimStatus.REFUTED


@dataclass
class FactCheckReport:
    """All verdicts for one run, with the derived decision-level status."""

    verdicts: list[ClaimVerdict] = field(default_factory=list)

    def add(self, verdict: ClaimVerdict) -> None:
        self.verdicts.append(verdict)

    @property
    def blocking_claim_ids(self) -> list[str]:
        return [v.claim_id for v in self.verdicts if v.blocks_decision]

    @property
    def refuted_claim_ids(self) -> list[str]:
        return [v.claim_id for v in self.verdicts if v.status is ClaimStatus.REFUTED]

    @property
    def blocks_decision(self) -> bool:
        """True when any refuted claim is blocking: the synthesis must not
        present an unqualified conclusion over it (contract §6)."""
        return bool(self.blocking_claim_ids)

    def summary(self) -> dict:
        """Machine-readable summary for the audit trail and the report."""
        return {
            "total_claims": len(self.verdicts),
            "supported": sum(1 for v in self.verdicts
                             if v.status is ClaimStatus.SUPPORTED),
            "unverified": sum(1 for v in self.verdicts
                              if v.status is ClaimStatus.UNVERIFIED),
            "refuted": len(self.refuted_claim_ids),
            "blocking_claims": self.blocking_claim_ids,
        }


def check_claim(
    claim: Claim,
    registry: ProvenanceRegistry,
    *,
    post_event_status: str | None = None,
) -> ClaimVerdict:
    """Check one claim against the run's verified facts.

    The rules, in order:

    - A causal-inference claim about a market reaction is refuted when the
      causal guard says the post-event prices are not yet observable
      (``EVENT_AFTER_LAST_MARKET_SESSION`` / ``POST_EVENT_PRICES_UNAVAILABLE``).
    - A claim with no supporting fact ids cannot be more than a hypothesis:
      presented as FACT or DERIVED_CALCULATION it is refuted as
      ``NO_SUPPORTING_FACTS``; presented as HYPOTHESIS/FORECAST it is
      ``UNVERIFIED`` (an opinion, allowed as long as it is labelled one).
    - Supporting facts that are not in the registry, or are not verified,
      downgrade the claim: missing ids refute, unverified/quarantined ids
      mark the claim UNVERIFIED.
    - Verified supporting facts uphold the claim.
    """
    # Causal claims checked against the causal guard's verdict.
    if claim.classification is ClaimClassification.CAUSAL_INFERENCE:
        if post_event_status == NOT_YET_OBSERVABLE:
            return ClaimVerdict(
                claim_id=claim.claim_id, statement=claim.statement,
                classification=claim.classification,
                supporting_fact_ids=claim.supporting_fact_ids,
                status=ClaimStatus.REFUTED,
                reason_code=ReasonCode.EVENT_AFTER_LAST_MARKET_SESSION,
                blocking=claim.blocking,
            )
        if post_event_status is None:
            return ClaimVerdict(
                claim_id=claim.claim_id, statement=claim.statement,
                classification=claim.classification,
                supporting_fact_ids=claim.supporting_fact_ids,
                status=ClaimStatus.UNVERIFIED,
                reason_code=ReasonCode.POST_EVENT_PRICES_UNAVAILABLE,
                blocking=claim.blocking,
            )

    # Support requirements by classification.
    if not claim.supporting_fact_ids:
        if claim.classification in (ClaimClassification.FACT,
                                    ClaimClassification.DERIVED_CALCULATION):
            return ClaimVerdict(
                claim_id=claim.claim_id, statement=claim.statement,
                classification=claim.classification,
                supporting_fact_ids=(),
                status=ClaimStatus.REFUTED,
                reason_code=ReasonCode.NO_SUPPORTING_FACTS,
                blocking=claim.blocking,
            )
        # A labelled hypothesis or forecast is an opinion: unverified, not
        # refuted — but a *blocking* hypothesis stated without support is
        # the HYPOTHESIS_STATED_AS_FACT failure the contract calls out.
        return ClaimVerdict(
            claim_id=claim.claim_id, statement=claim.statement,
            classification=claim.classification,
            supporting_fact_ids=(),
            status=ClaimStatus.UNVERIFIED,
            reason_code=(ReasonCode.HYPOTHESIS_STATED_AS_FACT if claim.blocking
                         else ReasonCode.NO_SUPPORTING_FACTS),
            blocking=claim.blocking,
        )

    # Supporting facts must exist in the registry and be verified.
    missing = [fid for fid in claim.supporting_fact_ids if registry.get(fid) is None]
    if missing:
        return ClaimVerdict(
            claim_id=claim.claim_id, statement=claim.statement,
            classification=claim.classification,
            supporting_fact_ids=claim.supporting_fact_ids,
            status=ClaimStatus.REFUTED,
            reason_code=ReasonCode.CONTRADICTED_BY_REGISTRY,
            blocking=claim.blocking,
        )
    not_verified = [
        fid for fid in claim.supporting_fact_ids
        if registry.get(fid) is not None and not registry.get(fid).is_usable
    ]
    if not_verified:
        statuses = {registry.get(fid).verification_status for fid in not_verified}
        reason = (ReasonCode.SUPPORTING_FACTS_QUARANTINED if "quarantined" in statuses
                  else ReasonCode.SUPPORTING_FACTS_UNVERIFIED)
        return ClaimVerdict(
            claim_id=claim.claim_id, statement=claim.statement,
            classification=claim.classification,
            supporting_fact_ids=claim.supporting_fact_ids,
            status=ClaimStatus.UNVERIFIED,
            reason_code=reason,
            blocking=claim.blocking,
        )

    return ClaimVerdict(
        claim_id=claim.claim_id, statement=claim.statement,
        classification=claim.classification,
        supporting_fact_ids=claim.supporting_fact_ids,
        status=ClaimStatus.SUPPORTED,
        reason_code=ReasonCode.OK,
        blocking=claim.blocking,
    )


def check_claims(
    claims: list[Claim],
    registry: ProvenanceRegistry,
    *,
    post_event_status: str | None = None,
) -> FactCheckReport:
    """Check every claim; the report carries the decision-level verdict."""
    report = FactCheckReport()
    for claim in claims:
        report.add(check_claim(claim, registry, post_event_status=post_event_status))
    return report
