import asyncio
import threading
import time
import pytest
from datetime import datetime, timezone

from web.server import db, runner
from web.server.tests.fixtures.fake_graph import FakeTradingAgents, happy_path, RateLimitError


@pytest.mark.asyncio
async def test_happy_path_emits_and_persists(monkeypatch, temp_db):
    monkeypatch.setattr(runner, "build_graph", lambda config=None: FakeTradingAgents(happy_path("NVDA")))
    monkeypatch.setattr(runner.events, "emit", lambda rid, t, d: db.append_event(rid, t, d))

    await runner.start(num_workers=1)
    try:
        rid = runner.enqueue("NVDA", idempotency_key="NVDA:2026-06-01")
        # wait for the queue worker to finish
        await runner._wait_for_idle(timeout=5)

        run = db.get_run(rid)
        assert run.status == "done"
        assert run.decision_action == "BUY"
        assert run.decision_target == 260.0

        events = db.events_for_run(rid)
        types = [e.type for e in events]
        assert "run_started" in types
        assert "analyst_thinking" in types
        assert "debate_message" in types
        assert "decision" in types
        assert "run_finished" in types
    finally:
        await runner.stop()


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency(monkeypatch, temp_db):
    from web.server.tests.fixtures.fake_graph import ScriptedRun, ScriptedNode

    started = []
    release = threading.Event()

    def slow_graph(config=None):
        class Slow:
            def propagate(self_inner, ticker, trade_date, *, event_callback=None):
                started.append(ticker)
                release.wait()
                return {"decision": {"action": "HOLD"}}
        return Slow()

    monkeypatch.setattr(runner, "build_graph", slow_graph)
    monkeypatch.setattr(runner.events, "emit", lambda rid, t, d: db.append_event(rid, t, d))
    monkeypatch.setattr(runner, "MAX_CONCURRENT", 2)

    await runner.start(num_workers=3)
    try:
        runner.enqueue("A", idempotency_key="A:k")
        runner.enqueue("B", idempotency_key="B:k")
        runner.enqueue("C", idempotency_key="C:k")

        # wait until 2 are running
        for _ in range(50):
            if len(started) >= 2:
                break
            await asyncio.sleep(0.05)
        assert len(started) == 2

        # release the held jobs
        release.set()
        await runner._wait_for_idle(timeout=5)
        assert len(started) == 3
    finally:
        await runner.stop()


@pytest.mark.asyncio
async def test_cancellation_emits_run_failed(monkeypatch, temp_db):
    from web.server.tests.fixtures.fake_graph import ScriptedRun, ScriptedNode

    started = threading.Event()
    release = threading.Event()

    def blocking_graph(config=None):
        class Blocking:
            def propagate(self_inner, ticker, trade_date, *, event_callback=None):
                started.set()
                while not release.is_set():
                    if event_callback is not None:
                        event_callback("node_entered", {"node": "blocking"})
                    time.sleep(0.05)
                return {}
        return Blocking()

    monkeypatch.setattr(runner, "build_graph", blocking_graph)
    monkeypatch.setattr(runner.events, "emit", lambda rid, t, d: db.append_event(rid, t, d))

    await runner.start(num_workers=1)
    try:
        rid = runner.enqueue("NVDA", idempotency_key="NVDA:cancel")
        while not started.is_set():
            await asyncio.sleep(0.05)
        db.request_cancellation(rid)
        release.set()
        await runner._wait_for_idle(timeout=5)

        run = db.get_run(rid)
        assert run.status == "failed"
        assert "cancel" in (run.decision_rationale or "").lower()
    finally:
        await runner.stop()
