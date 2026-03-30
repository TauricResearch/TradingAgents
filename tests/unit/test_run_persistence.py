import asyncio

import pytest

from agent_os.backend.routes import runs as runs_route
from tradingagents.portfolio import store_factory


class _FakeStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def save_run_events(self, date: str, events: list[dict]) -> None:
        self.calls.append(("events", {"date": date, "count": len(events)}))

    def save_run_meta(self, date: str, meta: dict) -> None:
        self.calls.append(("meta", {"date": date, "status": meta.get("status")}))


def test_persist_run_to_disk_writes_events_before_meta(monkeypatch):
    fake_store = _FakeStore()
    monkeypatch.setattr(store_factory, "create_report_store", lambda run_id=None: fake_store)

    run_id = "run-persist-order"
    runs_route.runs[run_id] = {
        "id": run_id,
        "type": "scan",
        "status": "running",
        "created_at": 1,
        "user_id": "u",
        "params": {"date": "2026-03-31"},
        "events": [{"type": "log", "message": "x"}],
        "rerun_seq": 0,
    }

    try:
        runs_route._persist_run_to_disk(run_id)
    finally:
        runs_route.runs.pop(run_id, None)

    assert fake_store.calls == [
        ("events", {"date": "2026-03-31", "count": 1}),
        ("meta", {"date": "2026-03-31", "status": "running"}),
    ]


def test_run_and_store_checkpoints_events_before_cancellation(monkeypatch):
    fake_store = _FakeStore()
    monkeypatch.setattr(store_factory, "create_report_store", lambda run_id=None: fake_store)

    run_id = "run-checkpoint"
    runs_route.runs[run_id] = {
        "id": run_id,
        "type": "auto",
        "status": "running",
        "created_at": 1,
        "user_id": "u",
        "params": {"date": "2026-03-31"},
        "events": [],
        "rerun_seq": 0,
    }

    async def _gen():
        for i in range(10):
            yield {"type": "log", "message": str(i)}
        raise asyncio.CancelledError()

    try:
        asyncio.run(runs_route._run_and_store(run_id, _gen()))
        run_snapshot = dict(runs_route.runs[run_id])
    finally:
        runs_route.runs.pop(run_id, None)

    event_counts = [payload["count"] for kind, payload in fake_store.calls if kind == "events"]
    meta_statuses = [payload["status"] for kind, payload in fake_store.calls if kind == "meta"]

    assert event_counts == list(range(1, 11)) + [10]
    assert meta_statuses == ["failed"]
    assert run_snapshot["status"] == "failed"
    assert run_snapshot["error"] == "Run cancelled"


def test_run_and_store_checkpoints_first_event(monkeypatch):
    fake_store = _FakeStore()
    monkeypatch.setattr(store_factory, "create_report_store", lambda run_id=None: fake_store)

    run_id = "run-first-event"
    runs_route.runs[run_id] = {
        "id": run_id,
        "type": "scan",
        "status": "running",
        "created_at": 1,
        "user_id": "u",
        "params": {"date": "2026-03-31"},
        "events": [],
        "rerun_seq": 0,
    }

    async def _gen():
        yield {"type": "log", "message": "first"}
        raise asyncio.CancelledError()

    try:
        asyncio.run(runs_route._run_and_store(run_id, _gen()))
    finally:
        runs_route.runs.pop(run_id, None)

    event_counts = [payload["count"] for kind, payload in fake_store.calls if kind == "events"]
    assert event_counts == [1, 1]
