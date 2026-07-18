"""SSE wire contracts for durable replay and live run observation."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tradingagents.observability.events import PersistedEvent, RunEventDraft
from tradingagents.web.broker import Keepalive, SubscriptionClosed
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import RunStore

pytestmark = pytest.mark.unit


def _create_app(**kwargs: Any):
    from tradingagents.web.api import create_app

    return create_app(**kwargs)


def _run(store: RunStore, *, status: str = "running") -> RunSnapshot:
    snapshot = RunSnapshot.create(
        ticker="AAPL",
        analysis_date="2026-07-18",
        selected_analysts=("market",),
        llm_provider="openai",
        quick_think_llm="gpt-5.4-mini",
        deep_think_llm="gpt-5.5",
    ).evolve(status=status)
    store.create_run(snapshot)
    return snapshot


class NoopManager:
    active_run_id = None

    def __init__(self) -> None:
        self.cancel_calls: list[str] = []

    def cancel(self, run_id: str):
        self.cancel_calls.append(run_id)
        raise AssertionError("an SSE disconnect must never cancel the analysis")


class ScriptedSubscription:
    def __init__(self, items: list[PersistedEvent | Keepalive], *, block: bool = False):
        self.items = deque(items)
        self.block = block
        self.close_calls: list[str] = []
        self.closed_reason: str | None = None
        self._never = asyncio.Event()

    async def next_event(self, *, timeout: float | None = None):
        del timeout
        if self.items:
            return self.items.popleft()
        if self.block:
            await self._never.wait()
        raise SubscriptionClosed("terminal")

    async def close(self, reason: str = "client_disconnected") -> None:
        self.close_calls.append(reason)
        self.closed_reason = reason
        self._never.set()

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.next_event()
        except SubscriptionClosed as exc:
            if exc.reason == "terminal":
                raise StopAsyncIteration from exc
            raise


class ScriptedBroker:
    def __init__(self, subscription: ScriptedSubscription) -> None:
        self.subscription = subscription
        self.calls: list[dict[str, Any]] = []

    async def subscribe(self, run_id: str, **kwargs: Any):
        self.calls.append({"run_id": run_id, **kwargs})
        return self.subscription


def _event(run_id: str, sequence: int, event_type: str = "future.sse_test") -> PersistedEvent:
    return PersistedEvent.from_draft(
        RunEventDraft(run_id, event_type, {"value": sequence}),
        sequence,
    )


def _parse_sse(body: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for frame in body.split("\n\n"):
        if not frame:
            continue
        if frame.startswith(":"):
            parsed.append({"comment": frame[1:].strip()})
            continue
        fields: dict[str, Any] = {}
        for line in frame.splitlines():
            name, value = line.split(":", 1)
            fields[name] = value.lstrip()
        fields["data"] = json.loads(fields["data"])
        parsed.append(fields)
    return parsed


@pytest.mark.parametrize(
    ("query", "headers", "expected_after"),
    [
        ("?after=4", {}, 4),
        ("", {"Last-Event-ID": "7"}, 7),
        ("?after=9", {"Last-Event-ID": "9"}, 9),
    ],
)
def test_sse_honors_after_and_last_event_id(
    tmp_path: Path,
    query: str,
    headers: dict[str, str],
    expected_after: int,
):
    store = RunStore(tmp_path / "runs")
    run = _run(store, status="failed")
    subscription = ScriptedSubscription([])
    broker = ScriptedBroker(subscription)
    client = TestClient(_create_app(store=store, manager=NoopManager(), broker=broker))

    response = client.get(f"/api/runs/{run.run_id}/events{query}", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert broker.calls == [
        {
            "run_id": run.run_id,
            "after": expected_after,
            "close_after_replay": True,
        }
    ]


def test_conflicting_resume_cursors_are_rejected_before_subscription(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    run = _run(store)
    broker = ScriptedBroker(ScriptedSubscription([]))
    client = TestClient(_create_app(store=store, manager=NoopManager(), broker=broker))

    response = client.get(
        f"/api/runs/{run.run_id}/events?after=4",
        headers={"Last-Event-ID": "7"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "event_cursor_mismatch"
    assert broker.calls == []


@pytest.mark.parametrize(
    ("query", "headers"),
    [
        ("?after=-1", {}),
        ("?after=not-an-int", {}),
        ("", {"Last-Event-ID": "-1"}),
        ("", {"Last-Event-ID": "not-an-int"}),
    ],
)
def test_invalid_event_cursor_is_rejected(
    tmp_path: Path,
    query: str,
    headers: dict[str, str],
):
    store = RunStore(tmp_path / "runs")
    run = _run(store)
    broker = ScriptedBroker(ScriptedSubscription([]))
    client = TestClient(_create_app(store=store, manager=NoopManager(), broker=broker))

    response = client.get(f"/api/runs/{run.run_id}/events{query}", headers=headers)

    assert response.status_code in {400, 422}
    assert broker.calls == []


def test_sse_serializes_the_complete_persisted_envelope_and_keepalive(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    run = _run(store, status="failed")
    event = store.append_event(
        RunEventDraft(run.run_id, "future.sse_test", {"value": 1})
    )
    subscription = ScriptedSubscription([event, Keepalive()])
    broker = ScriptedBroker(subscription)
    client = TestClient(_create_app(store=store, manager=NoopManager(), broker=broker))

    response = client.get(f"/api/runs/{run.run_id}/events")

    assert response.status_code == 200
    frames = _parse_sse(response.text)
    assert frames == [
        {
            "id": "1",
            "event": event.type,
            "data": event.as_dict(),
        },
        {"comment": "keepalive"},
    ]
    assert subscription.close_calls


def test_terminal_stream_closes_after_replay_watermark(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    run = _run(store, status="failed")
    store.append_event(RunEventDraft(run.run_id, "future.sse_test", {"value": 1}))
    second = store.append_event(
        RunEventDraft(run.run_id, "future.sse_test", {"value": 2})
    )
    subscription = ScriptedSubscription([second])
    broker = ScriptedBroker(subscription)
    client = TestClient(_create_app(store=store, manager=NoopManager(), broker=broker))

    response = client.get(f"/api/runs/{run.run_id}/events?after=1")

    assert response.status_code == 200
    assert [frame["data"]["sequence"] for frame in _parse_sse(response.text)] == [2]
    assert broker.calls[0]["close_after_replay"] is True
    assert subscription.close_calls


def test_nonterminal_stream_subscribes_live(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    run = _run(store, status="running")
    subscription = ScriptedSubscription([_event(run.run_id, 1)])
    broker = ScriptedBroker(subscription)
    client = TestClient(_create_app(store=store, manager=NoopManager(), broker=broker))

    response = client.get(f"/api/runs/{run.run_id}/events")

    assert response.status_code == 200
    assert broker.calls[0]["close_after_replay"] is False


def test_live_terminal_event_closes_an_initially_nonterminal_stream(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    run = _run(store, status="running")
    terminal = PersistedEvent.from_draft(
        RunEventDraft(
            run.run_id,
            "run.failed",
            {"run_status": "failed", "summary": "safe failure"},
        ),
        1,
    )
    subscription = ScriptedSubscription([terminal], block=True)
    broker = ScriptedBroker(subscription)
    client = TestClient(_create_app(store=store, manager=NoopManager(), broker=broker))

    response = client.get(f"/api/runs/{run.run_id}/events")

    assert response.status_code == 200
    assert [frame["event"] for frame in _parse_sse(response.text)] == ["run.failed"]
    assert broker.calls[0]["close_after_replay"] is False
    assert subscription.close_calls


def test_client_disconnect_unsubscribes_but_never_cancels_run(tmp_path: Path):
    async def scenario() -> None:
        store = RunStore(tmp_path / "runs")
        run = _run(store, status="running")
        subscription = ScriptedSubscription([_event(run.run_id, 1)], block=True)
        broker = ScriptedBroker(subscription)
        manager = NoopManager()
        app = _create_app(store=store, manager=manager, broker=broker)
        first_body_sent = asyncio.Event()
        receive_count = 0
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            nonlocal receive_count
            receive_count += 1
            if receive_count == 1:
                return {"type": "http.request", "body": b"", "more_body": False}
            await first_body_sent.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)
            if message["type"] == "http.response.body" and message.get("body"):
                first_body_sent.set()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": f"/api/runs/{run.run_id}/events",
            "raw_path": f"/api/runs/{run.run_id}/events".encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
            "state": {},
        }

        await asyncio.wait_for(app(scope, receive, send), timeout=2)

        assert any(message["type"] == "http.response.body" for message in sent)
        assert subscription.close_calls
        assert manager.cancel_calls == []
        assert store.read_snapshot(run.run_id).status == "running"

    asyncio.run(scenario())
