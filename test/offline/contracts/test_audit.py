"""Offline tests for the public audit contract :mod:`egta.contracts.audit`.

Covers (D items 3,4,11): AuditContractError hierarchy + exception signatures,
Receipt's 12 typed fields + extra rejection, AuditSink.append idempotency,
fail-closed (AuditUnavailable), cross-run identity, AuditReader sorting + run
scope, empty chain, first-event prev non-empty, tail-truncation + external anchor.

``_InMemorySink`` below is a **reference double** used only to pin the contract
semantics in the spec; the implementation PR MUST add a real ``SqliteAuditSink``
integration test. RED on the spec branch.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from egta.contracts.audit import (
    AuditContractError,
    AuditReader,
    AuditSink,
    AuditUnavailable,
    ChainBroken,
    DuplicateConflict,
    PayloadMismatch,
    Receipt,
    SequenceConflict,
    recompute_payload_hash,
    verify_chain,
)
from egta.contracts.events import Phase, RunEvent, RunStatus

pytestmark = pytest.mark.spec

VALID_HASH = "a" * 64
RECEIPT_FIELDS = {
    "schema_version", "receipt_id", "run_id", "event_id", "sequence",
    "payload_hash", "prev_event_hash", "chain_tip_hash", "persisted_at",
    "store_id", "transaction_id", "idempotency_key",
}


def _utc() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _bound(seq: int, event_id: str, run_id: str = "r1", prev: str = "", **extra) -> RunEvent:
    base = {
        "schema_version": "1.0", "event_id": event_id, "run_id": run_id,
        "sequence": seq, "phase": Phase.APP, "timestamp": _utc(),
        "duration_ms": 0, "status": RunStatus.OK,
        "payload_hash": VALID_HASH, "prev_event_hash": prev, **extra,
    }
    draft = RunEvent(**base)
    return draft.model_copy(update={"payload_hash": recompute_payload_hash(draft)})


# --- exception hierarchy + signatures --------------------------------------


def test_audit_public_protocols_importable():
    assert AuditSink is not None
    assert AuditReader is not None


def test_exceptions_share_base():
    for cls in (ChainBroken, DuplicateConflict, PayloadMismatch, AuditUnavailable,
                SequenceConflict):
        assert issubclass(cls, AuditContractError)


def test_sequenceconflict_signature():
    exc = SequenceConflict("r1", 0, "e0", "e1")
    assert (exc.run_id, exc.sequence, exc.existing_event_id, exc.incoming_event_id) == (
        "r1", 0, "e0", "e1")


def test_chainbroken_signature():
    exc = ChainBroken("r1", 2, 4, "gap")
    assert (exc.run_id, exc.expected_sequence, exc.actual_sequence, exc.reason) == ("r1", 2, 4, "gap")


def test_duplicateconflict_signature():
    exc = DuplicateConflict("r1", "e1", "a" * 64, "b" * 64)
    assert (exc.run_id, exc.event_id, exc.existing_payload_hash, exc.incoming_payload_hash) == (
        "r1", "e1", "a" * 64, "b" * 64)


def test_payloadmismatch_signature():
    exc = PayloadMismatch("r1", "e1", "a" * 64, "b" * 64)
    assert (exc.run_id, exc.event_id, exc.stored_payload_hash, exc.recomputed_payload_hash) == (
        "r1", "e1", "a" * 64, "b" * 64)


def test_auditunavailable_signature():
    exc = AuditUnavailable("r1", "append", "disk full")
    assert (exc.run_id, exc.operation, exc.cause) == ("r1", "append", "disk full")


# --- Receipt: exactly D's 12 typed fields -----------------------------------


def test_receipt_has_exactly_twelve_fields():
    assert set(Receipt.model_fields) == RECEIPT_FIELDS
    assert len(Receipt.model_fields) == 12


def test_receipt_rejects_extra_field():
    payload = dict.fromkeys(RECEIPT_FIELDS, "x")
    payload.update({"persisted_at": _utc(), "sequence": 0, "thirteenth": "no"})
    with pytest.raises(ValidationError):
        Receipt(**payload)


def test_receipt_type_validation():
    payload = dict.fromkeys(RECEIPT_FIELDS, "x")
    payload.update({"persisted_at": _utc(), "sequence": "not-int"})
    with pytest.raises(ValidationError):
        Receipt(**payload)


# --- verify_chain edge cases ------------------------------------------------


def test_empty_chain_is_ok():
    assert verify_chain([]) is None


def test_first_event_prev_must_be_empty():
    bad = _bound(0, "e0", prev="b" * 64)
    with pytest.raises(ChainBroken):
        verify_chain([bad])


def test_full_chain_with_correct_anchor_passes():
    ev0 = _bound(0, "e0")
    ev1 = _bound(1, "e1", prev=ev0.payload_hash)
    verify_chain([ev0, ev1], anchor=ev1.payload_hash)  # no raise


def test_tail_truncation_detected_with_anchor():
    ev0 = _bound(0, "e0")
    ev1 = _bound(1, "e1", prev=ev0.payload_hash)
    ev2 = _bound(2, "e2", prev=ev1.payload_hash)
    with pytest.raises(ChainBroken):
        verify_chain([ev0, ev1], anchor=ev2.payload_hash)


# --- AuditSink reference double (reference only; impl adds SqliteAuditSink) --

class _InMemorySink:
    """REFERENCE DOUBLE for spec semantics — NOT the production sink.

    The implementation PR must add a real ``SqliteAuditSink`` integration test.
    Supports fail-closed when ``fail=True``.
    """

    def __init__(self, *, fail: bool = False):
        self._by_key: dict[tuple[str, str], tuple[str, Receipt]] = {}
        self._by_run: dict[str, list[RunEvent]] = {}
        self._fail = fail

    def append(self, event: RunEvent) -> Receipt:
        if self._fail:
            raise AuditUnavailable(event.run_id, "append", "simulated storage failure")
        content = recompute_payload_hash(event)
        key = (event.run_id, event.event_id)  # identity = (run_id, event_id)
        existing = self._by_key.get(key)
        if existing is not None:
            old_content, old_receipt = existing
            if old_content != content:
                raise DuplicateConflict(event.run_id, event.event_id, old_content, content)
            return old_receipt
        receipt = Receipt(
            schema_version="1.0", receipt_id=f"rcpt-{event.run_id}-{event.event_id}",
            run_id=event.run_id, event_id=event.event_id, sequence=event.sequence,
            payload_hash=event.payload_hash, prev_event_hash=event.prev_event_hash,
            chain_tip_hash=content, persisted_at=_utc(), store_id="mem",
            transaction_id="tx1", idempotency_key=f"{event.run_id}:{event.event_id}",
        )
        self._by_key[key] = (content, receipt)
        self._by_run.setdefault(event.run_id, []).append(event)
        return receipt

    def read(self, run_id: str):
        return _Reader(sorted(self._by_run.get(run_id, []), key=lambda e: e.sequence))


class _Reader:
    def __init__(self, events):
        self._events = events

    def read(self, run_id: str):
        return [e for e in self._events if e.run_id == run_id]


def test_sink_same_id_same_content_returns_existing_receipt():
    sink = _InMemorySink()
    ev = _bound(0, "e0")
    assert sink.append(ev).receipt_id == sink.append(ev).receipt_id
    assert len(sink.read("r1").read("r1")) == 1


def test_sink_same_id_diff_content_rejected():
    sink = _InMemorySink()
    sink.append(_bound(0, "e0"))
    with pytest.raises(DuplicateConflict):
        sink.append(_bound(0, "e0", metrics={"different": True}))


def test_sink_cross_run_same_event_id_not_conflicting():
    """Same event_id under DIFFERENT run_id is not a conflict."""
    sink = _InMemorySink()
    sink.append(_bound(0, "e0", run_id="r1"))
    sink.append(_bound(0, "e0", run_id="r2"))  # no raise
    assert len(sink.read("r2").read("r2")) == 1


def test_sink_fail_closed_no_partial_write():
    sink = _InMemorySink(fail=True)
    with pytest.raises(AuditUnavailable):
        sink.append(_bound(0, "e0"))
    assert sink.read("r1").read("r1") == []  # nothing persisted


def test_reader_sorts_and_scopes_by_run():
    sink = _InMemorySink()
    ev0 = _bound(0, "e0")
    ev1 = _bound(1, "e1", prev=ev0.payload_hash)
    sink.append(ev1)  # out of order on purpose
    sink.append(ev0)
    sink.append(_bound(0, "x0", run_id="other"))
    read = sink.read("r1").read("r1")
    assert [e.sequence for e in read] == [0, 1]
    assert all(e.run_id == "r1" for e in read)
