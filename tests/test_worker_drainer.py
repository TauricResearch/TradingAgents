"""Tests for :mod:`worker_drainer`. The most important one is
:func:`test_does_not_block_on_full_pipe` — that's the actual production
deadlock the module is built to prevent."""
from __future__ import annotations

import subprocess
import sys
import textwrap
import time

import pytest

from worker_drainer import WorkerDrainer


def _make_worker_script(
    n_chunks: int, payload_bytes: int = 100, trailing: str = "done",
) -> str:
    """Python source that, when run as -c, emits ``n_chunks`` chunk events
    plus an optional terminating event."""
    return textwrap.dedent(f"""
        import json, sys
        for i in range({n_chunks}):
            sys.stdout.write(json.dumps({{
                "kind": "chunk",
                "data": {{"i": i, "pad": "x" * {payload_bytes}}},
            }}) + "\\n")
            sys.stdout.flush()
        trailing = {trailing!r}
        if trailing == "done":
            sys.stdout.write(json.dumps({{"kind": "done", "decision": "BUY"}}) + "\\n")
        elif trailing == "error":
            sys.stdout.write(json.dumps({{
                "kind": "error", "type": "BoomError", "msg": "kaboom",
            }}) + "\\n")
        elif trailing == "garbage":
            sys.stdout.write("not-json garbage\\n")
        sys.stdout.flush()
    """)


def _spawn(script: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-u", "-c", script],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, encoding="utf-8",
    )


def _wait_for_eof(drainer: WorkerDrainer, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while not drainer.eof and time.time() < deadline:
        time.sleep(0.05)
    assert drainer.eof, f"drainer didn't reach EOF in {timeout}s"


def test_collects_chunks_and_done_event() -> None:
    proc = _spawn(_make_worker_script(5))
    d = WorkerDrainer(proc)
    _wait_for_eof(d)
    proc.wait(timeout=2)
    assert [c["i"] for c in d.chunks] == [0, 1, 2, 3, 4]
    assert d.decision == "BUY"
    assert d.error is None


def test_records_error_event() -> None:
    proc = _spawn(_make_worker_script(2, trailing="error"))
    d = WorkerDrainer(proc)
    _wait_for_eof(d)
    proc.wait(timeout=2)
    assert d.decision is None
    assert d.error is not None
    assert d.error["type"] == "BoomError"
    assert d.error["msg"] == "kaboom"


def test_does_not_block_on_full_pipe() -> None:
    """Production bug: webui worker fills the 64 KB pipe buffer before any
    UI session reads it, then deadlocks on pipe_write. Drainer must consume
    the pipe in real time so the writer can always make progress.

    1000 chunks × ~200 B ≈ 200 KB — comfortably past the 64 KB buffer."""
    proc = _spawn(_make_worker_script(1000, payload_bytes=200))
    d = WorkerDrainer(proc)
    _wait_for_eof(d, timeout=10)
    rc = proc.wait(timeout=3)
    assert rc == 0
    assert len(d.chunks) == 1000
    assert d.decision == "BUY"


def test_garbage_lines_are_skipped_not_fatal() -> None:
    """A non-JSON line on stdout (e.g. a stray print) must not kill the
    drainer or stop subsequent valid events from being recorded."""
    proc = _spawn(_make_worker_script(3, trailing="garbage"))
    d = WorkerDrainer(proc)
    _wait_for_eof(d)
    proc.wait(timeout=2)
    # Drainer survived the garbage line; chunks before it were captured.
    assert len(d.chunks) == 3
    # No 'done' was sent → decision stays None, no spurious error.
    assert d.decision is None
    assert d.error is None


def test_snapshot_chunks_returns_independent_copy() -> None:
    """Caller must not be able to mutate the drainer's internal list by
    holding a reference to the snapshot return value."""
    proc = _spawn(_make_worker_script(3))
    d = WorkerDrainer(proc)
    _wait_for_eof(d)
    proc.wait(timeout=2)
    snap = d.snapshot_chunks()
    snap.append({"polluter": True})
    snap2 = d.snapshot_chunks()
    assert len(snap2) == 3
    assert all("polluter" not in c for c in snap2)


def test_thread_is_daemon_so_it_doesnt_keep_process_alive() -> None:
    proc = _spawn(_make_worker_script(1))
    d = WorkerDrainer(proc)
    _wait_for_eof(d)
    proc.wait(timeout=2)
    assert d._thread.daemon is True
