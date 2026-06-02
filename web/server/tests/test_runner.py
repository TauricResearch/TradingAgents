import asyncio
import json
import threading
import time
import pytest
from datetime import datetime, timezone

from web.server import db, runner
from web.server.tests.fixtures.fake_graph import FakeTradingAgents, happy_path, RateLimitError


def _payload(event) -> dict:
    """Parse Event.payload_json into a dict (the model stores data as JSON)."""
    return json.loads(event.payload_json)


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


@pytest.mark.asyncio
async def test_rate_limit_exhaustion_emits_warnings_and_run_failed(monkeypatch, temp_db):
    """All 4 attempts hit a rate limit; final event has reason=rate_limited
    and exactly 3 tool_call_warning events were persisted in between."""
    class _AlwaysRateLimitError(RuntimeError):
        pass

    def always_failing_graph(config=None):
        class _Failing:
            def propagate(self_inner, ticker, trade_date, *, event_callback=None):
                raise _AlwaysRateLimitError(
                    "Error calling model 'gemini-3.5-flash' (RESOURCE_EXHAUSTED): 429. "
                    "'retryDelay': '0.05s'"
                )
        return _Failing()

    monkeypatch.setattr(runner, "build_graph", always_failing_graph)
    monkeypatch.setattr(runner.events, "emit", lambda rid, t, d: db.append_event(rid, t, d))

    await runner.start(num_workers=1)
    try:
        rid = runner.enqueue("NVDA", idempotency_key="NVDA:rl-exhaust")
        await runner._wait_for_idle(timeout=10)

        events_list = db.events_for_run(rid)
        warnings = [e for e in events_list if e.type == "tool_call_warning"]
        run_failed = [e for e in events_list if e.type == "run_failed"]

        # 3 retries (MAX_ATTEMPTS=4 → 3 sleeps before the final attempt fails).
        assert len(warnings) == 3, [_payload(w) for w in warnings]
        for w in warnings:
            data = _payload(w)
            assert data.get("retry_after_s") is not None
            assert data.get("exception_class") == "_AlwaysRateLimitError"
            # 0.05s hint is well under the 60s cap, so the hint is used.
            assert 0 < data["retry_after_s"] <= 0.1

        # Final failure: rate_limited, with the original message preserved.
        assert len(run_failed) == 1
        failed_data = _payload(run_failed[0])
        assert failed_data["reason"] == "rate_limited"
        assert failed_data["exception_class"] == "_AlwaysRateLimitError"
        assert "RESOURCE_EXHAUSTED" in failed_data["message"]

        run = db.get_run(rid)
        assert run.status == "failed"
    finally:
        await runner.stop()


@pytest.mark.asyncio
async def test_rate_limit_recovered_after_two_attempts(monkeypatch, temp_db):
    """First two attempts raise a rate-limit; third succeeds. The run ends
    'done', with exactly 2 tool_call_warning events and a run_finished."""
    class _RateLimitError(RuntimeError):
        pass

    counter = {"calls": 0}

    def flaky_graph(config=None):
        class _Flaky:
            def propagate(self_inner, ticker, trade_date, *, event_callback=None):
                counter["calls"] += 1
                if counter["calls"] <= 2:
                    raise _RateLimitError("'retryDelay': '0.01s'")
                return {"decision": {"action": "HOLD"}}
        return _Flaky()

    monkeypatch.setattr(runner, "build_graph", flaky_graph)
    monkeypatch.setattr(runner.events, "emit", lambda rid, t, d: db.append_event(rid, t, d))

    await runner.start(num_workers=1)
    try:
        rid = runner.enqueue("AAPL", idempotency_key="AAPL:rl-recover")
        await runner._wait_for_idle(timeout=5)

        run = db.get_run(rid)
        assert run.status == "done"
        assert run.decision_action == "HOLD"

        events_list = db.events_for_run(rid)
        warnings = [e for e in events_list if e.type == "tool_call_warning"]
        run_finished = [e for e in events_list if e.type == "run_finished"]
        run_failed = [e for e in events_list if e.type == "run_failed"]

        assert len(warnings) == 2
        assert len(run_finished) == 1
        assert len(run_failed) == 0
    finally:
        await runner.stop()
