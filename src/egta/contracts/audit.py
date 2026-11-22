"""Public audit contract (implements the approved FR-05 spec).

# Implements: FR-05, NFR-08, NFR-09

Defines the typed exceptions (``AuditContractError`` base), the 12-field
``Receipt``, the ``AuditSink``/``AuditReader`` protocols, and the free functions
``recompute_payload_hash`` / ``verify_payload`` / ``verify_chain`` /
``dedupe_events``. The real ``SqliteAuditSink`` lives in
``src/egta/evaluation/sink.py`` (Phase 2, delivered with its own test/spec PR).
Definitions: docs/req/contracts-summary.md §1.

Tamper-evidence: ``verify_chain`` proves internal consistency (payload binding,
gap-free ``(run_id, sequence)``, ``prev_event_hash`` links) and, given an
``anchor`` (external trusted tip), detects tail truncation / whole-chain
replacement. The chain alone is not authenticity against a log-rewriting
attacker; an external anchor is required for that.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from egta.contracts.events import RunEvent


class AuditContractError(Exception):
    """Base for all audit-contract failures."""


class ChainBroken(AuditContractError):
    """A chain link, sequence, genesis, or anchor-tip check failed."""

    def __init__(self, run_id: str, expected_sequence: int, actual_sequence: int, reason: str):
        self.run_id = run_id
        self.expected_sequence = expected_sequence
        self.actual_sequence = actual_sequence
        self.reason = reason
        super().__init__(
            f"ChainBroken(run_id={run_id!r}, expected={expected_sequence}, "
            f"actual={actual_sequence}, reason={reason!r})"
        )


class DuplicateConflict(AuditContractError):
    """Same (run_id, event_id) seen with different content."""

    def __init__(self, run_id: str, event_id: str,
                 existing_payload_hash: str, incoming_payload_hash: str):
        self.run_id = run_id
        self.event_id = event_id
        self.existing_payload_hash = existing_payload_hash
        self.incoming_payload_hash = incoming_payload_hash
        super().__init__(
            f"DuplicateConflict(run_id={run_id!r}, event_id={event_id!r})"
        )


class PayloadMismatch(AuditContractError):
    """A recomputed payload hash does not match the stored one."""

    def __init__(self, run_id: str, event_id: str,
                 stored_payload_hash: str, recomputed_payload_hash: str):
        self.run_id = run_id
        self.event_id = event_id
        self.stored_payload_hash = stored_payload_hash
        self.recomputed_payload_hash = recomputed_payload_hash
        super().__init__(
            f"PayloadMismatch(run_id={run_id!r}, event_id={event_id!r})"
        )


class SequenceConflict(AuditContractError):
    """Two different events share the same (run_id, sequence)."""

    def __init__(self, run_id: str, sequence: int,
                 existing_event_id: str, incoming_event_id: str):
        self.run_id = run_id
        self.sequence = sequence
        self.existing_event_id = existing_event_id
        self.incoming_event_id = incoming_event_id
        super().__init__(
            f"SequenceConflict(run_id={run_id!r}, sequence={sequence}, "
            f"existing={existing_event_id!r}, incoming={incoming_event_id!r})"
        )


class AuditUnavailable(AuditContractError):
    """The audit store/anchor could not be written (fail-closed)."""

    def __init__(self, run_id: str, operation: str, cause: str):
        self.run_id = run_id
        self.operation = operation
        self.cause = cause
        super().__init__(
            f"AuditUnavailable(run_id={run_id!r}, operation={operation!r}, cause={cause!r})"
        )


class Receipt(BaseModel):
    """Proof of a persisted append; exactly twelve fields."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    receipt_id: str
    run_id: str
    event_id: str
    sequence: int = Field(strict=True)
    payload_hash: str
    prev_event_hash: str
    chain_tip_hash: str
    persisted_at: datetime
    store_id: str
    transaction_id: str
    idempotency_key: str

    @field_validator("persisted_at")
    @classmethod
    def _require_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("persisted_at must be timezone-aware (UTC)")
        return value.astimezone(UTC)


def recompute_payload_hash(event: RunEvent) -> str:
    """Canonical SHA-256 (lowercase hex) of the event's content, excluding hash."""
    payload = event.model_dump(mode="json", exclude={"payload_hash"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_payload(event: RunEvent) -> None:
    """Raise ``PayloadMismatch`` if the stored hash is not the recomputed one."""
    recomputed = recompute_payload_hash(event)
    if recomputed != event.payload_hash:
        raise PayloadMismatch(event.run_id, event.event_id, event.payload_hash, recomputed)


def dedupe_events(events: list[RunEvent]) -> list[RunEvent]:
    """Collapse identical (run_id, event_id) to one; conflict -> DuplicateConflict.

    Preserves first-seen order.
    """
    seen: dict[tuple[str, str], str] = {}
    out: list[RunEvent] = []
    for event in events:
        content = recompute_payload_hash(event)
        key = (event.run_id, event.event_id)
        if key in seen:
            if seen[key] != content:
                raise DuplicateConflict(event.run_id, event.event_id, seen[key], content)
            continue
        seen[key] = content
        out.append(event)
    return out


def verify_chain(events: list[RunEvent], *, anchor: str | None = None) -> None:
    """Verify payload binding, gap-free sequence, links, and an optional anchor.

    Args:
        events: the run's events (any order).
        anchor: trusted external tip hash. If given and the chain's actual tip
            differs, tail truncation / whole-chain replacement is detected.

    Raises:
        DuplicateConflict, PayloadMismatch, ChainBroken.
    """
    if not events:
        if anchor is not None:
            raise ChainBroken("", 0, -1, "empty chain cannot satisfy an anchor (fail-closed)")
        return
    events = dedupe_events(events)
    ordered = sorted(events, key=lambda e: (e.run_id, e.sequence))
    run_id = ordered[0].run_id
    if ordered[0].prev_event_hash != "":
        raise ChainBroken(run_id, 0, ordered[0].sequence, "genesis prev_event_hash not empty")
    last = -1
    for event in ordered:
        if event.sequence != last + 1:
            raise ChainBroken(event.run_id, last + 1, event.sequence, "sequence gap")
        last = event.sequence
        verify_payload(event)
    for prev, cur in zip(ordered, ordered[1:], strict=False):
        if cur.prev_event_hash != prev.payload_hash:
            raise ChainBroken(cur.run_id, prev.sequence + 1, cur.sequence, "link broken")
    if anchor is not None and ordered[-1].payload_hash != anchor:
        raise ChainBroken(run_id, last, last, "tip != anchor (tail truncation)")


class AuditReader(Protocol):
    """Read one run's events, sorted by sequence."""

    def read(self, run_id: str) -> list[RunEvent]: ...


class AuditSink(Protocol):
    """Append receipts and open per-run readers (hybrid read API)."""

    def append(self, event: RunEvent) -> Receipt: ...

    def read(self, run_id: str) -> AuditReader: ...
