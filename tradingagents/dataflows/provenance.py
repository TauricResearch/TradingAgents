"""Provenance registry for material facts (Phase 1, contract section 3.1).

Every numeric fact an analysis relies on carries where it came from, when it
was published and when it was retrieved. A fact without provenance is
``UNVERIFIED`` and cannot feed a rating, a target or an order; the Execution
Gate (Phase 3) reads these statuses, so the vocabulary here is the contract's.

The registry is deliberately small and pure: it records and classifies, it
never fetches. Vendors fill in what they know; anything they do not know
stays ``unknown`` rather than being invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# Verification statuses, ordered from strongest to weakest. The contract's
# blocking rules key off these names; keep them stable.
VERIFIED = "verified"
UNVERIFIED = "unverified"
QUARANTINED = "quarantined"

# Source types a fact may carry. ``unknown`` is a real value: a vendor that
# does not say what kind of source it served must not be guessed into one.
SOURCE_TYPES = frozenset({
    "company_release",
    "sec_filing",
    "vendor_api",
    "news_article",
    "prediction_market",
    "derived_calculation",
    "unknown",
})


class ProvenanceError(ValueError):
    """A fact was built with impossible provenance (e.g. published before its period ended)."""


@dataclass(frozen=True)
class Fact:
    """One material fact with its provenance.

    ``published_at`` is when the source made the fact public (ISO-8601 with
    offset when known, ``None`` when not verified). ``retrieved_at`` is when
    this system fetched it. They are different moments and neither implies
    the other; a fact with no ``published_at`` is ``UNVERIFIED`` no matter
    how fresh its retrieval was.
    """

    fact_id: str
    value: object
    unit: str
    period: str | None
    period_end: str | None          # YYYY-MM-DD or None
    source_type: str
    source_uri: str | None
    published_at: datetime | None
    retrieved_at: datetime
    snapshot_id: str
    verification_status: str = UNVERIFIED
    notes: str = ""

    def __post_init__(self):
        if self.source_type not in SOURCE_TYPES:
            raise ProvenanceError(
                f"source_type {self.source_type!r} is not one of {sorted(SOURCE_TYPES)}"
            )
        if self.verification_status not in (VERIFIED, UNVERIFIED, QUARANTINED):
            raise ProvenanceError(
                f"verification_status {self.verification_status!r} is not one of "
                f"{VERIFIED!r}, {UNVERIFIED!r}, {QUARANTINED!r}"
            )
        if self.published_at is not None and self.period_end is not None:
            published = self.published_at
            period_end = datetime.strptime(self.period_end, "%Y-%m-%d").replace(tzinfo=UTC)
            if published < period_end:
                raise ProvenanceError(
                    f"fact {self.fact_id!r} published {published:%Y-%m-%d} before its "
                    f"period ended {self.period_end}: impossible provenance"
                )

    @property
    def is_usable(self) -> bool:
        """Whether the fact may feed a rating, target or order.

        A verified fact is usable. An unverified one is not: it may be shown
        as context but must not drive a decision. A quarantined one is
        contested (e.g. vendor metrics that disagree) and is excluded until
        reconciled.
        """
        return self.verification_status == VERIFIED

    def published_date(self) -> str | None:
        """The publication date as YYYY-MM-DD, or None when unknown."""
        return f"{self.published_at:%Y-%m-%d}" if self.published_at else None


@dataclass
class ProvenanceRegistry:
    """The facts recorded for one analysis snapshot.

    One registry per run; ``snapshot_id`` ties every fact to the shared
    as-of snapshot it was read from, so agents cannot mix vintages silently.
    """

    snapshot_id: str
    facts: dict[str, Fact] = field(default_factory=dict)

    def add(self, fact: Fact) -> Fact:
        """Record a fact; re-registering the same fact_id replaces it."""
        if fact.snapshot_id != self.snapshot_id:
            raise ProvenanceError(
                f"fact {fact.fact_id!r} belongs to snapshot {fact.snapshot_id!r}, "
                f"not this registry's {self.snapshot_id!r}"
            )
        self.facts[fact.fact_id] = fact
        return fact

    def get(self, fact_id: str) -> Fact | None:
        return self.facts.get(fact_id)

    def usable_facts(self) -> list[Fact]:
        """Facts that may feed decisions, in registration order."""
        return [f for f in self.facts.values() if f.is_usable]

    def blocking_fact_ids(self) -> list[str]:
        """Facts that must not feed decisions, for the audit trail."""
        return [fid for fid, f in self.facts.items() if not f.is_usable]

    def summary(self) -> dict:
        """Machine-readable provenance summary for the audit trail."""
        return {
            "snapshot_id": self.snapshot_id,
            "total_facts": len(self.facts),
            "usable": len(self.usable_facts()),
            "blocking": self.blocking_fact_ids(),
        }


def verified_fact(
    fact_id: str,
    value,
    unit: str,
    *,
    period: str | None,
    period_end: str | None,
    source_type: str,
    source_uri: str | None,
    published_at: datetime | None,
    retrieved_at: datetime,
    snapshot_id: str,
    notes: str = "",
) -> Fact:
    """Build a VERIFIED fact: the caller vouches for publication and source."""
    return Fact(
        fact_id=fact_id,
        value=value,
        unit=unit,
        period=period,
        period_end=period_end,
        source_type=source_type,
        source_uri=source_uri,
        published_at=published_at,
        retrieved_at=retrieved_at,
        snapshot_id=snapshot_id,
        verification_status=VERIFIED,
        notes=notes,
    )


def unverified_fact(fact_id: str, value, unit: str, *, snapshot_id: str,
                    reason: str = "publication time not verified") -> Fact:
    """Build an UNVERIFIED fact: usable as context, never as a decision input."""
    return Fact(
        fact_id=fact_id,
        value=value,
        unit=unit,
        period=None,
        period_end=None,
        source_type="unknown",
        source_uri=None,
        published_at=None,
        retrieved_at=datetime.now(UTC),
        snapshot_id=snapshot_id,
        verification_status=UNVERIFIED,
        notes=reason,
    )
