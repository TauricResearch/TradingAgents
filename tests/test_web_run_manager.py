"""RunManager contract: single-run invariant (incl. draining), event log
monotonicity, terminal events, idempotent cancel, crash surfacing."""

import asyncio
import time

import pytest

from tradingagents.web.runs import RunConflictError, RunManager

pytestmark = pytest.mark.unit


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _idle_engine(params, emit):
    await asyncio.sleep(3600)


@pytest.mark.anyio
async def test_run_completes_with_done_event_and_result():
    seen_params = {}

    async def engine(params, emit):
        seen_params.update(params)
        emit("agent_status", {"agent": "Market Analyst", "status": "working"})
        return {"decision": "BUY"}

    manager = RunManager(engine)
    run = manager.start({"ticker": "AAPL", "date": "2026-07-01"})
    await manager.join(run)

    # The engine stamps run_id into the manifest — it must be injected.
    assert seen_params["run_id"] == run.id

    assert run.state == "done"
    assert run.result == {"decision": "BUY"}
    types = [e.type for e in run.events]
    assert types[0] == "run_status"
    assert types[-1] == "done"
    assert [e.id for e in run.events] == list(range(1, len(run.events) + 1))
    assert manager.active_run is None


@pytest.mark.anyio
async def test_crash_surfaces_error_event_and_failed_state():
    async def engine(params, emit):
        raise RuntimeError("boom")

    manager = RunManager(engine)
    run = manager.start({"ticker": "AAPL"})
    await manager.join(run)

    assert run.state == "failed"
    last = run.events[-1]
    assert last.type == "error"
    assert last.data["message"] == "boom"
    assert last.data["exc_type"] == "RuntimeError"
    assert isinstance(last.data["traceback_tail"], list)
    assert manager.active_run is None


@pytest.mark.anyio
async def test_second_start_while_active_raises_conflict():
    manager = RunManager(_idle_engine)
    run = manager.start({"ticker": "AAPL"})
    with pytest.raises(RunConflictError) as exc_info:
        manager.start({"ticker": "MSFT"})
    assert exc_info.value.active_run_id == run.id

    manager.cancel(run.id)
    await manager.join(run)
    assert run.state == "cancelled"
    assert run.events[-1].type == "cancelled"


@pytest.mark.anyio
async def test_cancel_is_idempotent():
    manager = RunManager(_idle_engine)
    run = manager.start({"ticker": "AAPL"})
    manager.cancel(run.id)
    manager.cancel(run.id)  # second cancel: no-op, no error
    await manager.join(run)
    manager.cancel(run.id)  # cancel after terminal: still fine
    assert run.state == "cancelled"
    assert [e.type for e in run.events].count("cancelled") == 1
    assert manager.cancel("nope") is None


@pytest.mark.anyio
async def test_draining_holds_single_run_slot_until_threads_finish():
    release = asyncio.Event()
    started = asyncio.Event()

    async def engine(params, emit):
        loop = asyncio.get_running_loop()
        started.set()
        # Detached sync work on the (per-run) default executor.
        await loop.run_in_executor(None, time.sleep, 0.3)

    manager = RunManager(engine)
    run = manager.start({"ticker": "AAPL"})
    await started.wait()
    await asyncio.sleep(0.05)  # ensure the thread is actually sleeping
    manager.cancel(run.id)

    # Terminal event lands promptly, but the slot stays held while the
    # orphaned thread drains.
    while run.state == "running":
        await asyncio.sleep(0.01)
    assert run.state == "cancelled"
    assert manager.active_run is run
    with pytest.raises(RunConflictError):
        manager.start({"ticker": "MSFT"})

    await manager.join(run)
    assert manager.active_run is None
    run2 = manager.start({"ticker": "MSFT"})
    manager.cancel(run2.id)
    release.set()
    await manager.join(run2)


@pytest.mark.anyio
async def test_subscribe_replays_and_tails_until_terminal():
    proceed = asyncio.Event()

    async def engine(params, emit):
        emit("report_section", {"section": "market_report", "markdown": "one"})
        await proceed.wait()
        emit("report_section", {"section": "market_report", "markdown": "two"})
        return {}

    manager = RunManager(engine)
    run = manager.start({"ticker": "AAPL"})
    await asyncio.sleep(0.01)

    received = []

    async def consume():
        async for event in manager.subscribe(run, after_id=0):
            received.append(event)

    consumer = asyncio.get_running_loop().create_task(consume())
    await asyncio.sleep(0.02)
    proceed.set()
    await manager.join(run)
    await consumer

    types = [e.type for e in received]
    assert types[0] == "run_status"
    assert types.count("report_section") == 2
    assert types[-1] == "done"
    assert [e.id for e in received] == sorted(e.id for e in received)


@pytest.mark.anyio
async def test_subscribe_from_last_event_id_skips_replayed_events():
    async def engine(params, emit):
        for i in range(5):
            emit("message", {"agent": "x", "preview": str(i)})
        return {}

    manager = RunManager(engine)
    run = manager.start({"ticker": "AAPL"})
    await manager.join(run)

    replay = [e async for e in manager.subscribe(run, after_id=3)]
    assert [e.id for e in replay] == list(range(4, len(run.events) + 1))
    assert replay[-1].type == "done"


@pytest.mark.anyio
async def test_new_run_discards_previous_event_log():
    async def engine(params, emit):
        return {}

    manager = RunManager(engine)
    first = manager.start({"ticker": "AAPL"})
    await manager.join(first)
    second = manager.start({"ticker": "MSFT"})
    await manager.join(second)

    assert manager.get(first.id) is None
    assert manager.get(second.id) is second
