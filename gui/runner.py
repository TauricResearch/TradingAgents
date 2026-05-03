"""Main-process subprocess manager.

A ``RunnerHandle`` wraps one in-flight worker. The Streamlit page stashes
the handle in ``st.session_state`` so it survives reruns, drains
``poll_events()`` each refresh, and renders accumulated state.

The reader thread reads stdout line-by-line, parses NDJSON, and pushes onto
a ``queue.Queue``. Stderr is captured in full and surfaced on completion if
the subprocess exits with a non-zero code.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import queue
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RunnerHandle:
    proc: subprocess.Popen
    events: "queue.Queue[Dict[str, Any]]"
    reader_thread: threading.Thread
    stderr_buf: List[str] = field(default_factory=list)
    job_path: Optional[Path] = None
    finished: bool = False
    return_code: Optional[int] = None
    drained: bool = False

    def poll_events(self) -> List[Dict[str, Any]]:
        """Drain whatever events have arrived since the last call.

        ``drained`` flips true only once the subprocess has exited AND the
        stdout reader thread has finished — at that point every event is
        guaranteed to be in the queue. Until both happen we don't claim
        the run is over even if ``proc.poll()`` says it exited.
        """
        out: List[Dict[str, Any]] = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                break
        if self.proc.poll() is not None:
            if self.return_code is None:
                self.return_code = self.proc.returncode
            if not self.reader_thread.is_alive() and not self.drained:
                self.drained = True
                self.finished = True
        return out

    def is_running(self) -> bool:
        """True until both the subprocess has exited and stdout is fully drained."""
        return not self.drained and (self.proc.poll() is None or self.reader_thread.is_alive())

    def cancel(self) -> None:
        if self.proc.poll() is None:
            try:
                if os.name == "nt":
                    self.proc.terminate()
                else:
                    self.proc.send_signal(signal.SIGTERM)
            except OSError:
                pass

    def cleanup(self) -> None:
        try:
            if self.job_path and self.job_path.exists():
                self.job_path.unlink()
        except OSError:
            pass


def _reader(stream, q: "queue.Queue[Dict[str, Any]]") -> None:
    for line in iter(stream.readline, ""):
        line = line.strip()
        if not line:
            continue
        try:
            q.put(json.loads(line))
        except json.JSONDecodeError:
            q.put({"type": "log", "content": line})
    stream.close()


def _stderr_reader(stream, buf: List[str]) -> None:
    for line in iter(stream.readline, ""):
        if line:
            buf.append(line)
    stream.close()


def launch(job: Dict[str, Any], *, env: Optional[Dict[str, str]] = None) -> RunnerHandle:
    """Spawn the worker subprocess and return a handle.

    ``job`` is dumped to a temp JSON file the worker reads at startup. ``env``
    overrides the default subprocess environment — pass the API-key-augmented
    env from ``gui.config.export_env`` so provider keys reach the worker.
    """
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(job, tmp)
    tmp.close()
    job_path = Path(tmp.name)

    repo_root = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, "-u", "-m", "gui.runner_worker", str(job_path)]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(repo_root),
        env=env if env is not None else os.environ.copy(),
        text=True,
        bufsize=1,
    )

    q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    stderr_buf: List[str] = []
    reader = threading.Thread(target=_reader, args=(proc.stdout, q), daemon=True)
    reader.start()
    threading.Thread(target=_stderr_reader, args=(proc.stderr, stderr_buf), daemon=True).start()

    return RunnerHandle(
        proc=proc,
        events=q,
        reader_thread=reader,
        stderr_buf=stderr_buf,
        job_path=job_path,
    )
