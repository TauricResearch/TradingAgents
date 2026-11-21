"""Offline tests for :func:`egta.contracts.evaluation.replay_events` (D item 6).

Asserts specific ReplayState content (not just "is not None"): fields, sorting,
dedupe, chain verification, determinism, input-order independence, duplicate
conflict, anchor/tail truncation, offline (socket poisoned) with content asserts.

Definitions: docs/req/contracts-summary.md §2. RED on the spec branch.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from egta.contracts.audit import ChainBroken, DuplicateConflict, recompute_payload_hash
from egta.contracts.evaluation import ReplayState, replay_events
from egta.contracts.events import Phase, RunEvent, RunStatus

pytestmark = pytest.mark.spec

VALID_HASH = "a" * 64


def _utc() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _bound(seq: int, event_id: str, run_id: str = "r1", prev: str = "", **extra) -> RunEvent:
    base = {
        "schema_version": "1.0", "event_id": event_id, "run_id": run_id,
        "sequence": seq, "phase": Phase.EVIDENCE, "timestamp": _utc(),
        "duration_ms": 0, "status": RunStatus.OK,
        "payload_hash": VALID_HASH, "prev_event_hash": prev, **extra,
    }
    draft = RunEvent(**base)
    return draft.model_copy(update={"payload_hash": recompute_payload_hash(draft)})


def _log():
    ev0 = _bound(0, "e0", metrics={"tokens": 10})
    ev1 = _bound(1, "e1", prev=ev0.payload_hash, metrics={"tokens": 5})
    return [ev0, ev1]


REPLAY_FIELDS = {"run_id", "last_sequence", "chain_tip_hash", "event_count",
                 "metrics", "events"}


def test_replay_state_has_expected_fields():
    state = replay_events(_log())
    assert isinstance(state, ReplayState)
    for f in REPLAY_FIELDS:
        assert hasattr(state, f)


def test_replay_state_content():
    log = _log()
    state = replay_events(log)
    assert state.run_id == "r1"
    assert state.last_sequence == 1
    assert state.event_count == 2
    assert state.chain_tip_hash == log[-1].payload_hash
    assert [e.event_id for e in state.events] == ["e0", "e1"]
    # metrics folded deterministically
    assert state.metrics == {"tokens": 5}


def test_replay_is_deterministic():
    log = _log()
    assert replay_events(log) == replay_events(log)


def test_replay_is_independent_of_input_order():
    ev0 = _bound(0, "e0", metrics={"tokens": 10})
    ev1 = _bound(1, "e1", prev=ev0.payload_hash, metrics={"tokens": 5})
    assert replay_events([ev0, ev1]) == replay_events([ev1, ev0])


def test_replay_dedupes_identical_events_once():
    log = _log()
    doubled = log + [log[0]]
    assert replay_events(doubled).event_count == 2


def test_replay_duplicate_conflict_raises():
    ev0 = _bound(0, "e0")
    conflict = _bound(0, "e0", metrics={"different": True})
    with pytest.raises(DuplicateConflict):
        replay_events([ev0, conflict])


def test_replay_anchor_mismatch_tail_truncation():
    ev0 = _bound(0, "e0")
    ev1 = _bound(1, "e1", prev=ev0.payload_hash)
    ev2 = _bound(2, "e2", prev=ev1.payload_hash)
    with pytest.raises(ChainBroken):
        replay_events([ev0, ev1], anchor=ev2.payload_hash)


def test_replay_is_offline_no_llm(monkeypatch):
    """Replay must not touch network; assert the returned CONTENT too."""
    import socket

    def _boom(*a, **k):
        raise AssertionError("replay must be offline: network/model touched")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom, raising=False)
    state = replay_events(_log())
    assert state.event_count == 2
    assert state.chain_tip_hash == _log()[-1].payload_hash
