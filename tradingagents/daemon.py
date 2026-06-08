"""Run the whole system in the background from the terminal.

    python -m tradingagents.cli start   # launches everything detached, returns
    python -m tradingagents.cli stop    # stops it
    python -m tradingagents.cli status  # is it running?

``start`` spawns a detached child that runs the autonomous loop, writes its PID
and streams output to ``~/.tradingagents/``. It returns immediately with a
one-line confirmation. ``stop`` signals that PID to shut down.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

_HOME = Path(os.path.expanduser("~")) / ".tradingagents"
_PID_FILE = _HOME / "agent.pid"
_LOG_FILE = _HOME / "agent.log"


def _read_pid() -> Optional[int]:
    try:
        return int(_PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)  # signal 0 = existence check
        return True
    except (OSError, ProcessLookupError):
        return False


def is_running() -> Optional[int]:
    pid = _read_pid()
    return pid if (pid is not None and _alive(pid)) else None


def start(interval: Optional[float] = None, *, config: Optional[str] = None,
          db: Optional[str] = None) -> str:
    """Launch the autonomous loop detached in the background. Returns a message."""
    running = is_running()
    if running:
        return f"trading-agent already running (pid {running}); use 'stop' first."

    _HOME.mkdir(parents=True, exist_ok=True)
    if interval is None:  # default loop period from config
        from .config import load_settings
        interval = load_settings(config).cycle.interval_seconds

    cmd = [sys.executable, "-m", "tradingagents.cli", "run", "--loop", str(interval)]
    if config:
        cmd += ["--config", config]
    if db:
        cmd += ["--db", db]

    log = open(_LOG_FILE, "a")
    proc = subprocess.Popen(
        cmd,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # detach from the controlling terminal
        cwd=os.getcwd(),
    )
    _PID_FILE.write_text(str(proc.pid))
    return (
        f"trading-agent started in background (pid {proc.pid}).\n"
        f"  logs:  {_LOG_FILE}\n"
        f"  stop:  python -m tradingagents.cli stop"
    )


def stop(*, timeout: float = 10.0) -> str:
    """Signal the background system to shut down. Returns a message."""
    pid = _read_pid()
    if pid is None:
        return "trading-agent is not running (no pid file)."
    if not _alive(pid):
        _PID_FILE.unlink(missing_ok=True)
        return f"trading-agent not running (stale pid {pid} cleared)."
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:  # pragma: no cover
        return f"could not stop pid {pid}: {exc}"
    _PID_FILE.unlink(missing_ok=True)
    return f"trading-agent stop signal sent (pid {pid})."


def status() -> str:
    pid = is_running()
    return (f"trading-agent is RUNNING (pid {pid})." if pid
            else "trading-agent is STOPPED.")
