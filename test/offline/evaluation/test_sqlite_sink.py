"""Offline spec: real SQLite sink :mod:`egta.evaluation.sink` (D#3).

Target: ``SqliteAuditSink`` in ``src/egta/evaluation/sink.py`` implementing
``egta.contracts.audit.AuditSink``/``AuditReader`` (contracts/audit.py keeps only
protocols/Receipt/exceptions/verify). Real SQLite integration test (D requirement).

Covers D's 6 items: idempotent append · duplicate conflict · cross-run identity ·
UNIQUE(run_id, sequence) · fail-closed (no partial write) · reader sorting/scope.

Red on this spec branch: ``egta.evaluation.sink`` / real sink absent.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from egta.contracts.audit import (
    AuditReader,
    AuditSink,
    AuditUnavailable,
    DuplicateConflict,
    Receipt,
    SequenceConflict,
    recompute_payload_hash,
)
from egta.contracts.events import Phase, RunEvent, RunStatus
from egta.evaluation.sink import SqliteAuditSink

pytestmark = pytest.mark.spec

H = "a" * 64


def _utc() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _bound(seq: int, event_id: str, run_id: str = "r1", prev: str = "", **extra) -> RunEvent:
    base = {
        "schema_version": "1.0", "event_id": event_id, "run_id": run_id,
        "sequence": seq, "phase": Phase.APP, "timestamp": _utc(),
        "duration_ms": 0, "status": RunStatus.OK,
        "payload_hash": H, "prev_event_hash": prev, **extra,
    }
    draft = RunEvent(**base)
    return draft.model_copy(update={"payload_hash": recompute_payload_hash(draft)})


def test_sink_satisfies_audit_protocols(tmp_path):
    """Conformance to AuditSink/AuditReader: runtime_checkable isinstance or inspect.signature."""
    import inspect

    sink = SqliteAuditSink(str(tmp_path / "audit.db"))
    if getattr(AuditSink, "_is_runtime_protocol", False):
        assert isinstance(sink, AuditSink)
    else:
        sig = inspect.signature(SqliteAuditSink.append)
        params = list(sig.parameters.values())
        assert params[1].name == "event"  # append(self, event)
        assert inspect.signature(SqliteAuditSink.read).parameters.get("run_id") is not None
    reader = sink.read("r1")
    assert inspect.signature(reader.read).parameters.get("run_id") is not None
    assert AuditReader is not None


def test_append_returns_receipt_with_12_fields(tmp_path):
    sink = SqliteAuditSink(str(tmp_path / "audit.db"))
    r = sink.append(_bound(0, "e0"))
    assert isinstance(r, Receipt)
    assert len(Receipt.model_fields) == 12
    assert r.run_id == "r1" and r.event_id == "e0"


def test_append_idempotent(tmp_path):
    sink = SqliteAuditSink(str(tmp_path / "audit.db"))
    ev = _bound(0, "e0")
    r1 = sink.append(ev)
    r2 = sink.append(ev)
    assert r1.receipt_id == r2.receipt_id
    assert len(sink.read("r1").read("r1")) == 1  # one row


def test_duplicate_conflict(tmp_path):
    sink = SqliteAuditSink(str(tmp_path / "audit.db"))
    sink.append(_bound(0, "e0"))
    with pytest.raises(DuplicateConflict):
        sink.append(_bound(0, "e0", metrics={"different": True}))


def test_cross_run_same_event_id_ok(tmp_path):
    sink = SqliteAuditSink(str(tmp_path / "audit.db"))
    sink.append(_bound(0, "e0", run_id="rA"))
    sink.append(_bound(0, "e0", run_id="rB"))  # no conflict across runs
    assert len(sink.read("rA").read("rA")) == 1
    assert len(sink.read("rB").read("rB")) == 1


def test_unique_run_sequence_is_sequence_conflict(tmp_path):
    """Two different event_ids at the same (run_id, sequence) -> SequenceConflict."""
    sink = SqliteAuditSink(str(tmp_path / "audit.db"))
    sink.append(_bound(0, "e0"))
    with pytest.raises(SequenceConflict):
        sink.append(_bound(0, "e1"))  # same sequence 0, different id


def test_fail_closed_no_partial_write(tmp_path):
    """A refused append leaves nothing persisted (no partial rows / receipt)."""
    sink = SqliteAuditSink(str(tmp_path / "audit.db"))
    sink.append(_bound(0, "e0"))
    with pytest.raises(SequenceConflict):
        sink.append(_bound(0, "e1"))
    assert [e.event_id for e in sink.read("r1").read("r1")] == ["e0"]


def test_reader_sorted_and_scoped(tmp_path):
    sink = SqliteAuditSink(str(tmp_path / "audit.db"))
    ev0 = _bound(0, "e0")
    ev1 = _bound(1, "e1", prev=ev0.payload_hash)
    sink.append(ev1)  # insert out of order
    sink.append(ev0)
    sink.append(_bound(0, "x0", run_id="other"))
    read = sink.read("r1").read("r1")
    assert [e.sequence for e in read] == [0, 1]
    assert all(e.run_id == "r1" for e in read)


def test_fail_closed_real_midprocess_failure_rolls_back(tmp_path):
    """A storage error after the event insert but before commit -> AuditUnavailable,
    transaction rolled back: no partial event row, no receipt."""
    sink = SqliteAuditSink(str(tmp_path / "audit.db"))
    # Force a failure on the receipts insert via a SQLite trigger.
    sink.conn.execute(
        "CREATE TRIGGER fail_receipt BEFORE INSERT ON receipts "
        "BEGIN SELECT RAISE(ABORT, 'injected receipt failure'); END;"
    )
    with pytest.raises(AuditUnavailable):
        sink.append(_bound(0, "e0"))
    # rollback: neither the event row nor a receipt persisted
    n_events = sink.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    n_receipts = sink.conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    assert n_events == 0 and n_receipts == 0
