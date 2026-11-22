"""Real SQLite audit sink (E2).

# Implements: FR-05, NFR-08, NFR-09

``SqliteAuditSink`` implements the public ``egta.contracts.audit``
``AuditSink``/``AuditReader`` protocols. One transaction per ``append`` writes the
event and its receipt atomically; UNIQUE(run_id, sequence) raises
``SequenceConflict`` and UNIQUE(run_id, event_id) with different content raises
``DuplicateConflict``; any real storage error (mid-write / disk) raises
``AuditUnavailable`` with the transaction rolled back — no partial rows, no
receipt (fail-closed).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from egta.contracts.audit import (
    AuditUnavailable,
    DuplicateConflict,
    Receipt,
    SequenceConflict,
    recompute_payload_hash,
)
from egta.contracts.events import RunEvent


class SqliteAuditReader:
    """``AuditReader`` for one run, sorted by sequence."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def read(self, run_id: str) -> list[RunEvent]:
        rows = self._conn.execute(
            "SELECT payload FROM events WHERE run_id = ? ORDER BY sequence ASC",
            (run_id,),
        ).fetchall()
        return [RunEvent.model_validate_json(row[0]) for row in rows]


class SqliteAuditSink:
    """Fail-closed, idempotent SQLite audit sink."""

    store_id = "sqlite"

    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (run_id, event_id),
                UNIQUE (run_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS receipts (
                idempotency_key TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            """
        )

    def append(self, event: RunEvent) -> Receipt:
        content = recompute_payload_hash(event)
        key = f"{event.run_id}:{event.event_id}"
        try:
            with self.conn:  # transaction: commit on success, rollback on error
                row = self.conn.execute(
                    "SELECT content_hash, payload FROM receipts WHERE idempotency_key = ?",
                    (key,),
                ).fetchone()
                if row is not None:
                    existing_content, payload_json = row
                    if existing_content != content:
                        raise DuplicateConflict(
                            event.run_id, event.event_id, existing_content, content
                        )
                    return Receipt.model_validate_json(payload_json)

                seq_row = self.conn.execute(
                    "SELECT event_id FROM events WHERE run_id = ? AND sequence = ?",
                    (event.run_id, event.sequence),
                ).fetchone()
                if seq_row is not None:
                    raise SequenceConflict(
                        event.run_id, event.sequence, seq_row[0], event.event_id
                    )

                receipt = Receipt(
                    schema_version="1.0",
                    receipt_id=f"rcpt-{key}",
                    run_id=event.run_id,
                    event_id=event.event_id,
                    sequence=event.sequence,
                    payload_hash=event.payload_hash,
                    prev_event_hash=event.prev_event_hash,
                    chain_tip_hash=content,
                    persisted_at=datetime.now(UTC),
                    store_id=self.store_id,
                    transaction_id=key,
                    idempotency_key=key,
                )
                self.conn.execute(
                    "INSERT INTO events (run_id, event_id, sequence, content_hash, payload) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (event.run_id, event.event_id, event.sequence, content,
                     event.model_dump_json()),
                )
                self.conn.execute(
                    "INSERT INTO receipts (idempotency_key, content_hash, payload) "
                    "VALUES (?, ?, ?)",
                    (key, content, receipt.model_dump_json()),
                )
                return receipt
        except (SequenceConflict, DuplicateConflict):
            raise
        except sqlite3.Error as exc:
            raise AuditUnavailable(event.run_id, "append", str(exc)) from exc

    def read(self, run_id: str) -> SqliteAuditReader:
        return SqliteAuditReader(self.conn)
