"""Run registry and lifecycle for the web server.

``RunManager`` owns the single-active-run invariant and the per-run event
log; the actual analysis work is delegated to an injected async *engine*
callable (``await engine(params, emit)``), which keeps the manager fully
testable without LLMs or the real graph.

Lifecycle: ``running`` -> ``done | failed | cancelled``. After the terminal
transition a run *drains*: cancellation lands at the current await, but the
in-flight sync node keeps running detached in its executor thread
(uninterruptible), so each run gets a dedicated ThreadPoolExecutor installed
as the loop default for its duration, and the single-run slot stays held
until that pool has fully shut down. Draining runs count as active.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import traceback
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

TERMINAL_EVENTS = frozenset({"done", "error", "cancelled"})

RUN_STATES = ("running", "done", "failed", "cancelled")

# Terminal event type emitted for each terminal state.
_STATE_EVENT = {"done": "done", "failed": "error", "cancelled": "cancelled"}

Emit = Callable[[str, dict], None]
Engine = Callable[[dict, Emit], Awaitable[dict | None]]


class RunConflictError(Exception):
    """A run is already active (or draining)."""

    def __init__(self, active_run_id: str):
        super().__init__(f"a run is already active: {active_run_id}")
        self.active_run_id = active_run_id


@dataclass
class Event:
    id: int
    type: str
    data: dict


@dataclass
class Run:
    id: str
    params: dict
    state: str = "running"
    draining: bool = False
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    result: dict | None = None
    error: dict | None = None
    events: list[Event] = field(default_factory=list)
    task: asyncio.Task | None = None
    _wakeup: asyncio.Event = field(default_factory=asyncio.Event)
    # Set once the run's single-run slot has been released (drain complete).
    released: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def terminal(self) -> bool:
        return self.state != "running"


class RunManager:
    def __init__(self, engine: Engine, max_pool_workers: int = 8):
        self._engine = engine
        self._max_pool_workers = max_pool_workers
        self._active: Run | None = None
        self._runs: dict[str, Run] = {}
        # Long-lived pool restored as the loop default while no run is active,
        # and used to await the drained run pool's shutdown.
        self._base_pool = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="web-base"
        )

    # -- queries ----------------------------------------------------------

    @property
    def active_run(self) -> Run | None:
        return self._active

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    # -- lifecycle --------------------------------------------------------

    def start(self, params: dict) -> Run:
        """Register and launch a run task. Raises RunConflictError if busy."""
        if self._active is not None:
            raise RunConflictError(self._active.id)

        run = Run(id=uuid.uuid4().hex[:12], params=dict(params))
        # The engine stamps this into the run.json manifest.
        run.params["run_id"] = run.id
        # The event log covers exactly one run: discard previous runs'
        # in-memory logs (completed runs are re-served from disk).
        self._runs.clear()
        self._runs[run.id] = run
        self._active = run

        self.emit(run, "run_status", {
            "state": "running",
            "run_id": run.id,
            "ticker": params.get("ticker"),
            "date": params.get("date"),
            "started_at": run.started_at,
        })
        # Strong reference kept in run.task / self._runs (GC safety).
        run.task = asyncio.get_running_loop().create_task(self._drive(run))
        # Safety net: a task cancelled before its first step raises at
        # coroutine entry — before _drive's try block can catch it — so the
        # terminal transition must also be guaranteed from the outside.
        run.task.add_done_callback(lambda task, run=run: self._on_task_done(run, task))
        return run

    def cancel(self, run_id: str) -> Run | None:
        """Idempotent cancel: only a still-running task is actually cancelled."""
        run = self._runs.get(run_id)
        if run is None:
            return None
        if not run.terminal and run.task is not None and not run.task.done():
            run.task.cancel()
        return run

    async def join(self, run: Run) -> None:
        """Wait for a run to finish *and* drain. Never raises the run's own
        CancelledError into the caller."""
        if run.task is not None:
            try:
                await run.task
            except asyncio.CancelledError:
                if not run.task.cancelled():
                    raise  # the caller was cancelled, not the run
        await run.released.wait()

    async def shutdown(self) -> None:
        """Cancel the active run and stop pools (server shutdown)."""
        run = self._active
        if run is not None and run.task is not None and not run.task.done():
            run.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await run.task
        self._base_pool.shutdown(wait=False, cancel_futures=True)

    # -- events -----------------------------------------------------------

    def emit(self, run: Run, event_type: str, data: dict) -> Event:
        event = Event(id=len(run.events) + 1, type=event_type, data=data)
        run.events.append(event)
        run._wakeup.set()
        return event

    async def subscribe(self, run: Run, after_id: int = 0):
        """Async-iterate events with id > after_id; replay then tail.

        Ends after yielding a terminal event (or immediately once the run is
        terminal and the log is exhausted). Single event loop: append +
        wakeup-set are atomic relative to coroutines, so the clear/re-check
        pattern below cannot lose a wakeup.
        """
        index = after_id
        while True:
            while index < len(run.events):
                event = run.events[index]
                index += 1
                yield event
                if event.type in TERMINAL_EVENTS:
                    return
            if run.terminal:
                return
            run._wakeup.clear()
            if index < len(run.events) or run.terminal:
                continue
            await run._wakeup.wait()

    # -- internals --------------------------------------------------------

    async def _drive(self, run: Run) -> None:
        loop = asyncio.get_running_loop()
        pool = ThreadPoolExecutor(
            max_workers=self._max_pool_workers,
            thread_name_prefix=f"run-{run.id}",
        )
        loop.set_default_executor(pool)

        def emit(event_type: str, data: dict) -> None:
            self.emit(run, event_type, data)

        try:
            result = await self._engine(run.params, emit)
            run.result = result if isinstance(result, dict) else None
            self._finish(run, "done", {"result": run.result})
        except asyncio.CancelledError:
            self._finish(run, "cancelled", {"run_id": run.id})
        except Exception as exc:
            tb_tail = traceback.format_exc().splitlines()[-20:]
            run.error = {
                "message": str(exc),
                "exc_type": type(exc).__name__,
                "traceback_tail": tb_tail,
            }
            self._finish(run, "failed", run.error)
        finally:
            # Terminal event is out; now drain. The slot (self._active) stays
            # held until every orphaned worker thread has finished, so a new
            # run can never overlap detached threads mutating shared state.
            loop.set_default_executor(self._base_pool)
            run.draining = True
            try:
                await loop.run_in_executor(self._base_pool, pool.shutdown)
            finally:
                run.draining = False
                self._release(run)

    def _on_task_done(self, run: Run, task: asyncio.Task) -> None:
        """Terminal-transition safety net for cancellation at coroutine entry."""
        if not run.terminal and task.cancelled():
            self._finish(run, "cancelled", {"run_id": run.id})
        if run.terminal and task.cancelled():
            # _drive never ran (no pool to drain): release directly.
            self._release(run)

    def _release(self, run: Run) -> None:
        if self._active is run:
            self._active = None
        run.released.set()

    def _finish(self, run: Run, state: str, data: dict) -> None:
        if run.terminal:
            return
        run.state = state
        run.finished_at = time.time()
        payload = dict(data)
        payload.setdefault("run_id", run.id)
        payload["state"] = state
        payload["finished_at"] = run.finished_at
        self.emit(run, _STATE_EVENT[state], payload)
