"""Phase 1 — provenance registry tests (contract section 3.1).

The registry records where each material fact came from, when it was
published and when retrieved. A fact without a verified publication time is
UNVERIFIED and must not feed a decision; a quarantined one is contested.
All tests are pure: no network, no LLM, frozen timestamps.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tradingagents.dataflows.provenance import (
    QUARANTINED,
    UNVERIFIED,
    VERIFIED,
    Fact,
    ProvenanceError,
    ProvenanceRegistry,
    unverified_fact,
    verified_fact,
)

_RETRIEVED = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
_PUBLISHED = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def _fact(**overrides):
    """A verified BRK-style fact; overrides retarget any field."""
    kwargs = {
        "fact_id": "q3_operating_earnings",
        "value": 12705,
        "unit": "USD_million",
        "period": "2026-Q3",
        "period_end": "2026-09-30",
        "source_type": "company_release",
        "source_uri": "https://example.com/release",
        "published_at": _PUBLISHED,
        "retrieved_at": _RETRIEVED,
        "snapshot_id": "snap-1",
        "verification_status": VERIFIED,
    }
    kwargs.update(overrides)
    return Fact(**kwargs)


@pytest.mark.unit
def test_verified_fact_is_usable_and_registry_records_it():
    reg = ProvenanceRegistry(snapshot_id="snap-1")
    fact = reg.add(_fact())
    assert fact.verification_status == VERIFIED
    assert fact.is_usable
    assert reg.usable_facts() == [fact]
    assert reg.blocking_fact_ids() == []


@pytest.mark.unit
def test_fact_without_published_at_is_unverified_and_blocking():
    """No publication time -> UNVERIFIED, however fresh the retrieval was."""
    fact = _fact(published_at=None, verification_status=UNVERIFIED)
    reg = ProvenanceRegistry(snapshot_id="snap-1")
    reg.add(fact)
    assert not fact.is_usable
    assert reg.blocking_fact_ids() == ["q3_operating_earnings"]


@pytest.mark.unit
def test_quarantined_fact_never_feeds_decisions():
    reg = ProvenanceRegistry(snapshot_id="snap-1")
    reg.add(_fact(verification_status=QUARANTINED, notes="vendor P/B mismatch"))
    assert reg.usable_facts() == []
    assert reg.blocking_fact_ids() == ["q3_operating_earnings"]


@pytest.mark.unit
def test_published_before_period_end_is_impossible_provenance():
    """A fact cannot be published before its reporting period ended."""
    with pytest.raises(ProvenanceError, match="before its period ended"):
        _fact(published_at=datetime(2026, 9, 29, tzinfo=UTC))


@pytest.mark.unit
def test_unknown_source_type_is_rejected_not_guessed():
    with pytest.raises(ProvenanceError, match="source_type"):
        _fact(source_type="i_saw_it_on_twitter")


@pytest.mark.unit
def test_fact_from_another_snapshot_is_refused():
    """Facts must belong to the registry's snapshot: no silent vintage mixing."""
    reg = ProvenanceRegistry(snapshot_id="snap-1")
    with pytest.raises(ProvenanceError, match="snapshot"):
        reg.add(_fact(snapshot_id="snap-2"))


@pytest.mark.unit
def test_published_date_helper_returns_date_only():
    assert _fact().published_date() == "2026-11-07"
    assert _fact(published_at=None).published_date() is None


@pytest.mark.unit
def test_unverified_factory_builds_blocking_context_fact():
    reg = ProvenanceRegistry(snapshot_id="snap-1")
    fact = reg.add(unverified_fact("rumor", 633.0, "USD", snapshot_id="snap-1"))
    assert fact.verification_status == UNVERIFIED
    assert fact.source_type == "unknown"
    assert not fact.is_usable


@pytest.mark.unit
def test_registry_summary_is_machine_readable():
    reg = ProvenanceRegistry(snapshot_id="snap-1")
    reg.add(_fact(fact_id="good"))
    reg.add(_fact(fact_id="bad", published_at=None, verification_status=UNVERIFIED))
    summary = reg.summary()
    assert summary == {
        "snapshot_id": "snap-1",
        "total_facts": 2,
        "usable": 1,
        "blocking": ["bad"],
    }


@pytest.mark.unit
def test_verified_factory_vouches_and_sets_status():
    fact = verified_fact(
        "f1", 42, "USD",
        period="2026-Q3", period_end="2026-09-30",
        source_type="sec_filing", source_uri="https://sec.gov/x",
        published_at=_PUBLISHED, retrieved_at=_RETRIEVED, snapshot_id="s",
    )
    assert fact.verification_status == VERIFIED
    assert fact.is_usable
