"""Drain a worker subprocess's stdout in a background thread.

The webui spawns ``worker.py`` via ``subprocess.Popen(stdout=PIPE)``. When the
user closes their browser, the streamlit script that was reading the pipe
stops running, but the worker keeps printing — fills the 64 KB pipe buffer —
and then blocks forever on the next write (``wchan == pipe_write``). The
``WorkerDrainer`` runs a daemon thread that reads the pipe regardless of
whether any UI session is attached, so the worker can always make progress.

Worker output protocol — one JSON object per line on stdout::

    {"kind": "started"}                                      # informational
    {"kind": "chunk",  "data": {...}}                         # incremental
    {"kind": "done",   "decision": "..."}                     # terminal-success
    {"kind": "error",  "type": "...", "msg": "...", "trace": "..."}  # terminal-fail
"""
from __future__ import annotations

import json
import threading
from typing import Any


class WorkerDrainer:
    """Owns a daemon thread that consumes ``proc.stdout`` and parses JSON
    events. Lives as long as the subprocess; thread exits on EOF.

    Thread-safe via an internal lock. Callers should treat ``decision``,
    ``error``, and ``eof`` as readable booleans/values; iterate ``chunks``
    only via :meth:`snapshot_chunks` to avoid races with the writer thread.
    """

    def __init__(self, proc: Any) -> None:
        self.proc = proc
        self.chunks: list[dict[str, Any]] = []
        self.decision: str | None = None
        self.error: dict[str, Any] | None = None
        self.eof: bool = False
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run,
            name=f"worker-drainer-{getattr(proc, 'pid', '?')}",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    print(
                        f"[worker non-JSON pid={getattr(self.proc, 'pid', '?')}] "
                        f"{line[:200]}",
                        flush=True,
                    )
                    continue
                kind = ev.get("kind")
                if kind == "chunk":
                    with self._lock:
                        self.chunks.append(ev.get("data", {}))
                elif kind == "done":
                    self.decision = ev.get("decision", "")
                elif kind == "error":
                    self.error = ev
                # "started" and unknown kinds intentionally ignored — caller
                # already knows the worker started, and unknown events
                # shouldn't crash the drainer.
        finally:
            self.eof = True

    def snapshot_chunks(self) -> list[dict[str, Any]]:
        """Return a shallow copy of the current chunks list. Safe to iterate
        and mutate without affecting the drainer's internal state."""
        with self._lock:
            return list(self.chunks)
