"""Offline spec: E2 replay orchestration :mod:`egta.evaluation.replay`.

Target: ``replay_run(events, *, run_id=None, anchor=None) -> ReplayState`` — a
thin orchestration over ``egta.contracts.evaluation.replay_events`` (dedupe-first,
``(run_id, sequence)`` sort, chain verify + anchor). Fully offline (no LLM/network).

Red on this spec branch: ``egta.evaluation.replay`` does not exist yet.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from egta.contracts.audit import (
    ChainBroken,
    DuplicateConflict,
    recompute_payload_hash,
)
from egta.contracts.evaluation import ReplayState
from egta.contracts.events import Phase, RunEvent, RunStatus
from egta.evaluation.replay import replay_run

pytestmark = pytest.mark.spec

H = "a" * 64


def _utc() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _bound(seq: int, event_id: str, run_id: str = "r1", prev: str = "", **extra) -> RunEvent:
    base = {
        "schema_version": "1.0", "event_id": event_id, "run_id": run_id,
        "sequence": seq, "phase": Phase.EVIDENCE, "timestamp": _utc(),
        "duration_ms": 0, "status": RunStatus.OK,
        "payload_hash": H, "prev_event_hash": prev, **extra,
    }
    draft = RunEvent(**base)
    return draft.model_copy(update={"payload_hash": recompute_payload_hash(draft)})


def _log():
    ev0 = _bound(0, "e0", metrics={"tokens": 10})
    ev1 = _bound(1, "e1", prev=ev0.payload_hash, metrics={"tokens": 5})
    return [ev0, ev1]


def test_replay_returns_replay_state():
    state = replay_run(_log())
    assert isinstance(state, ReplayState)
    assert state.run_id == "r1"
    assert state.last_sequence == 1
    assert state.event_count == 2


def test_replay_deterministic():
    log = _log()
    assert replay_run(log) == replay_run(log)


def test_replay_order_independent():
    ev0 = _bound(0, "e0", metrics={"tokens": 10})
    ev1 = _bound(1, "e1", prev=ev0.payload_hash, metrics={"tokens": 5})
    assert replay_run([ev0, ev1]) == replay_run([ev1, ev0])


def test_replay_dedupes_identical():
    log = _log()
    assert replay_run(log + [log[0]]).event_count == 2


def test_replay_duplicate_conflict_raises():
    ev0 = _bound(0, "e0")
    conflict = _bound(0, "e0", metrics={"different": True})
    with pytest.raises(DuplicateConflict):
        replay_run([ev0, conflict])


def test_replay_anchor_tail_truncation():
    ev0 = _bound(0, "e0")
    ev1 = _bound(1, "e1", prev=ev0.payload_hash)
    ev2 = _bound(2, "e2", prev=ev1.payload_hash)
    with pytest.raises(ChainBroken):
        replay_run([ev0, ev1], anchor=ev2.payload_hash)


def test_replay_offline_no_network(monkeypatch):
    import socket

    def _boom(*a, **k):
        raise AssertionError("replay must be offline: network touched")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom, raising=False)
    state = replay_run(_log())
    assert state.event_count == 2
    assert state.chain_tip_hash == _log()[-1].payload_hash


def test_replay_scopes_to_run_id():
    a0 = _bound(0, "e0", run_id="rA")
    b0 = _bound(0, "e0", run_id="rB")
    state = replay_run([a0, b0], run_id="rA")
    assert state.run_id == "rA"
    assert state.event_count == 1

