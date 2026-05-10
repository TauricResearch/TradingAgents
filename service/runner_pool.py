"""In-process registry of running analyses.

When a client POSTs to /runs, we spawn a worker subprocess (reusing the
existing ``gui.runner`` machinery — its `RunnerHandle` is exactly the
shape we need) and put its output queue into a fan-out.

When clients connect to the WebSocket /runs/{id}/stream, they each get
an asyncio.Queue subscribed to the run's event stream. The fan-out
reader thread reads NDJSON events from the worker stdout, dispatches
to all subscribers, and persists them to SQLite via ``gui.storage``
when terminal events arrive.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from gui import runner as legacy_runner
from gui import storage
from gui.config import export_env, load as load_config


@dataclass
class ManagedRun:
    run_id: str
    handle: legacy_runner.RunnerHandle
    subscribers: List["asyncio.Queue[Dict[str, Any]]"] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    decision: Optional[str] = None
    archive_path: Optional[str] = None
    error: Optional[str] = None
    warning: Optional[str] = None
    stats: Dict[str, int] = field(default_factory=lambda: {
        "llm_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0,
    })
    _lock: threading.Lock = field(default_factory=threading.Lock)


class RunnerPool:
    """Singleton-ish registry. Module-level instance below."""

    def __init__(self) -> None:
        self._runs: Dict[str, ManagedRun] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ---- Lifecycle ----------------------------------------------------

    def start(self, *, run_id: str, job: Dict[str, Any]) -> ManagedRun:
        cfg = load_config()
        env = export_env(cfg)
        # Inject run_id so the worker writes the right archive path.
        full_job = dict(job)
        full_job["run_id"] = run_id
        handle = legacy_runner.launch(full_job, env=env)

        managed = ManagedRun(run_id=run_id, handle=handle)
        with self._lock:
            self._runs[run_id] = managed

        # Background reader thread: drains the legacy queue and fans out.
        threading.Thread(
            target=self._reader_loop,
            args=(managed,),
            daemon=True,
        ).start()
        return managed

    def get(self, run_id: str) -> Optional[ManagedRun]:
        with self._lock:
            return self._runs.get(run_id)

    def cancel(self, run_id: str) -> bool:
        managed = self.get(run_id)
        if not managed:
            return False
        with managed._lock:
            if managed.finished:
                return False
        managed.handle.cancel()
        self._ingest(managed, {"type": "error", "message": "Cancelled by user."})
        self._mark_finished(managed)
        return True

    # ---- Subscriptions ------------------------------------------------

    async def subscribe(self, run_id: str) -> "asyncio.Queue[Dict[str, Any]]":
        """Return a queue that will receive every event for this run.

        Pre-existing events (sent before subscription) are replayed first
        so a late-arriving client still sees a full transcript.
        """
        managed = self.get(run_id)
        q: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
        if not managed:
            await q.put({"type": "error", "data": {"message": f"unknown run {run_id}"}})
            await q.put({"type": "_eof", "data": {}})
            return q
        with managed._lock:
            for ev in managed.history:
                await q.put(ev)
            if managed.finished:
                await q.put({"type": "_eof", "data": {}})
            else:
                managed.subscribers.append(q)
        return q

    def unsubscribe(self, run_id: str, q: "asyncio.Queue[Dict[str, Any]]") -> None:
        managed = self.get(run_id)
        if not managed:
            return
        with managed._lock:
            try:
                managed.subscribers.remove(q)
            except ValueError:
                pass

    # ---- Internal -----------------------------------------------------

    def _reader_loop(self, managed: ManagedRun) -> None:
        """Drain the legacy RunnerHandle and dispatch to subscribers + DB."""
        while True:
            events = managed.handle.poll_events()
            if events:
                for ev in events:
                    self._ingest(managed, ev)
            if not managed.handle.is_running() and not events:
                break
            # Short sleep — this is a thread, not asyncio.
            threading.Event().wait(0.25)

        # Final drain
        for ev in managed.handle.poll_events():
            self._ingest(managed, ev)
        self._mark_finished(managed)

    def _ingest(self, managed: ManagedRun, raw: Dict[str, Any]) -> None:
        # Normalise to {type, data} envelope expected by the schema.
        kind = raw.get("type", "log")
        data = {k: v for k, v in raw.items() if k != "type"}
        envelope = {"type": kind, "data": data}

        with managed._lock:
            managed.history.append(envelope)
            if kind == "stats":
                for k in ("llm_calls", "tool_calls", "tokens_in", "tokens_out"):
                    if k in data:
                        managed.stats[k] = data[k]
            elif kind == "warning":
                managed.warning = data.get("message")
            elif kind == "done":
                managed.decision = data.get("decision")
                managed.archive_path = data.get("archive_path") or data.get("report_path")
                # Persist to DB.
                try:
                    storage.update_run_stats(
                        managed.run_id,
                        llm_calls=managed.stats["llm_calls"],
                        tool_calls=managed.stats["tool_calls"],
                        tokens_in=managed.stats["tokens_in"],
                        tokens_out=managed.stats["tokens_out"],
                    )
                    storage.finalize_run(
                        managed.run_id,
                        decision=managed.decision,
                        log_path=managed.archive_path,
                    )
                except Exception:
                    pass
            elif kind == "error":
                managed.error = data.get("message", "unknown error")
                try:
                    storage.finalize_run(
                        managed.run_id,
                        decision=None,
                        log_path=None,
                        error=managed.error,
                    )
                except Exception:
                    pass
            subs = list(managed.subscribers)

        for q in subs:
            self._loop_call(q.put_nowait, envelope)

    def _mark_finished(self, managed: ManagedRun) -> None:
        with managed._lock:
            if managed.finished:
                return
            managed.finished = True
            subs = list(managed.subscribers)
            managed.subscribers.clear()
        for q in subs:
            self._loop_call(q.put_nowait, {"type": "_eof", "data": {}})

    def _loop_call(self, fn, *args, **kwargs) -> None:
        """Schedule a thread-safe call on the asyncio loop, falling back to
        direct call if no loop has been attached (shouldn't happen in
        normal operation but keeps unit tests simple)."""
        if self._loop is None or not self._loop.is_running():
            try:
                fn(*args, **kwargs)
            except Exception:
                pass
            return
        self._loop.call_soon_threadsafe(fn, *args, **kwargs)


pool = RunnerPool()
