"""Offline contract tests for :mod:`egta.contracts.events` (+ public audit helpers).

Strict negatives (no xfail/skip). Hash/chain via the PUBLIC audit contract
(:mod:`egta.contracts.audit`). RED on the spec branch (imports of
``egta.contracts.audit`` do not exist yet) = test-first signal.

Also covers D items 10/11: immutability (frozen/validate_assignment), sequence
strictness (negative/bool/string), status↔reason consistency, schema_version,
duration (NFR-09). Definitions: docs/req/contracts-summary.md.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from egta.contracts.audit import (
    ChainBroken,
    DuplicateConflict,
    PayloadMismatch,
    dedupe_events,
    recompute_payload_hash,
    verify_chain,
    verify_payload,
)
from egta.contracts.events import Phase, ReasonCode, RunEvent, RunStatus

pytestmark = pytest.mark.spec

VALID_HASH = "a" * 64


def _utc() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _event(**overrides) -> RunEvent:
    base = {
        "schema_version": "1.0",
        "event_id": "e1",
        "run_id": "r1",
        "sequence": 0,
        "phase": Phase.EVIDENCE,
        "timestamp": _utc(),
        "duration_ms": 0,
        "status": RunStatus.OK,
        "payload_hash": VALID_HASH,
        "prev_event_hash": "",
    }
    base.update(overrides)
    return RunEvent(**base)


def _bound(event_kwargs: dict) -> RunEvent:
    draft = _event(**event_kwargs)
    return draft.model_copy(update={"payload_hash": recompute_payload_hash(draft)})


# --- positive ----------------------------------------------------------------


def test_run_event_constructs():
    ev = _event(metrics={"tokens": 10})
    assert ev.run_id == "r1"
    assert ev.phase is Phase.EVIDENCE
    assert ev.status is RunStatus.OK
    assert ev.metrics == {"tokens": 10}
    assert ev.reason_code is None


def test_schema_version_present_and_validated():
    ev = _event(schema_version="1.0")
    assert ev.schema_version == "1.0"
    with pytest.raises(ValidationError):
        _event(schema_version="")


def test_reason_code_accepts_canonical_value():
    ev = _event(status=RunStatus.BLOCKED, reason_code=ReasonCode.BUDGET_DENIED)
    assert ev.reason_code is ReasonCode.BUDGET_DENIED


# --- immutability (F-05 / item 10) -----------------------------------------


def test_event_is_frozen_assignment_rejected():
    ev = _event()
    with pytest.raises(ValidationError):
        ev.sequence = 5  # type: ignore[misc]


# --- sequence strictness (F-20 / item 10/11) --------------------------------


@pytest.mark.parametrize("bad", [-1, True, "0", 1.5])
def test_sequence_must_be_strict_non_negative_int(bad):
    with pytest.raises(ValidationError):
        _event(sequence=bad)


# --- status <-> reason consistency (item 10) --------------------------------


def test_ok_must_not_carry_reason_code():
    with pytest.raises(ValidationError):
        _event(status=RunStatus.OK, reason_code=ReasonCode.BUDGET_DENIED)


def test_blocked_must_carry_reason_code():
    with pytest.raises(ValidationError):
        _event(status=RunStatus.BLOCKED, reason_code=None)


# --- duration (NFR-09) ------------------------------------------------------


def test_duration_non_negative():
    assert _event(duration_ms=0).duration_ms == 0
    with pytest.raises(ValidationError):
        _event(duration_ms=-1)


# --- negative: hashes --------------------------------------------------------


@pytest.mark.parametrize("bad", ["XYZ", "A" * 64, "a" * 63, "a" * 65, ""])
def test_payload_hash_must_be_64_lowercase_hex(bad):
    with pytest.raises(ValidationError):
        _event(payload_hash=bad)


@pytest.mark.parametrize("bad", ["abc", "A" * 64, "a" * 63])
def test_prev_event_hash_must_be_empty_or_64_lowercase_hex(bad):
    with pytest.raises(ValidationError):
        _event(prev_event_hash=bad)


def test_prev_event_hash_may_be_empty_for_first_event():
    assert _event(prev_event_hash="").prev_event_hash == ""


# --- negative: timezone ------------------------------------------------------


def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError):
        _event(timestamp=datetime(2026, 1, 2, 3, 4, 5))


def test_aware_timestamp_normalized_to_utc():
    tz8 = timezone(timedelta(hours=8))
    ev = _event(timestamp=datetime(2026, 1, 2, 11, 4, 5, tzinfo=tz8))
    assert ev.timestamp.utcoffset() == timedelta(0)
    assert ev.timestamp == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


# --- negative: schema strictness --------------------------------------------


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        _event(unexpected="x")


@pytest.mark.parametrize("bad", ["NOPE", "budget_denied", ""])
def test_illegal_reason_code_rejected(bad):
    with pytest.raises(ValidationError):
        _event(status=RunStatus.BLOCKED, reason_code=bad)


# --- public audit: payload binding + chain ----------------------------------


def test_recompute_payload_hash_is_deterministic():
    ev = _event(metrics={"b": 2, "a": 1})
    assert recompute_payload_hash(ev) == recompute_payload_hash(ev)
    ev2 = _event(metrics={"a": 1, "b": 2})
    assert recompute_payload_hash(ev) == recompute_payload_hash(ev2)


def test_verify_payload_rejects_recomputed_mismatch():
    good = _bound({"sequence": 0})
    verify_payload(good)  # no raise
    mutated = good.model_copy(update={"metrics": {"tokens": 999}})
    with pytest.raises(PayloadMismatch):
        verify_payload(mutated)


def test_hash_chain_links_and_tamper_breaks_it():
    ev1 = _bound({"sequence": 0})
    ev2 = _bound({"sequence": 1, "event_id": "e2",
                  "prev_event_hash": ev1.payload_hash})
    assert verify_chain([ev1, ev2]) is None
    tampered = [ev1.model_copy(update={"payload_hash": "f" * 64}), ev2]
    with pytest.raises(PayloadMismatch):
        verify_chain(tampered)


def test_chain_link_break_is_chainbroken():
    ev1 = _bound({"sequence": 0})
    ev2 = _bound({"sequence": 1, "event_id": "e2",
                  "prev_event_hash": ev1.payload_hash})
    ev1_forged = _bound({"sequence": 0, "metrics": {"forged": True}})
    with pytest.raises(ChainBroken):
        verify_chain([ev1_forged, ev2])


def test_sequence_gap_is_chainbroken():
    ev0 = _bound({"sequence": 0})
    ev2 = _bound({"sequence": 2, "event_id": "e3",
                  "prev_event_hash": ev0.payload_hash})
    with pytest.raises(ChainBroken):
        verify_chain([ev0, ev2])


# --- public audit: dedupe ----------------------------------------------------


def test_dedupe_identical_events_collapses_once():
    ev = _bound({"sequence": 0, "event_id": "same"})
    assert len(dedupe_events([ev, ev])) == 1


def test_dedupe_conflicting_event_id_raises():
    ev0 = _bound({"sequence": 0, "event_id": "dup"})
    ev1 = _bound({"sequence": 1, "event_id": "dup",
                  "prev_event_hash": ev0.payload_hash,
                  "metrics": {"different": True}})
    with pytest.raises(DuplicateConflict):
        dedupe_events([ev0, ev1])


def test_dedupe_preserves_order():
    ev0 = _bound({"sequence": 0, "event_id": "e0"})
    ev1 = _bound({"sequence": 1, "event_id": "e1",
                  "prev_event_hash": ev0.payload_hash})
    out = dedupe_events([ev1, ev0, ev1])
    assert [e.event_id for e in out] == ["e1", "e0"]
