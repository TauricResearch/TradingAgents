"""Tests for the background daemon (start/stop/status lifecycle)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from tradingagents import daemon

pytestmark = pytest.mark.unit


@pytest.fixture()
def isolated_home(tmp_path, monkeypatch):
    pid = tmp_path / "agent.pid"
    log = tmp_path / "agent.log"
    monkeypatch.setattr(daemon, "_HOME", tmp_path)
    monkeypatch.setattr(daemon, "_PID_FILE", pid)
    monkeypatch.setattr(daemon, "_LOG_FILE", log)
    yield tmp_path
    # cleanup any process we started
    running = daemon.is_running()
    if running:
        daemon.stop()


def test_status_when_stopped(isolated_home):
    assert daemon.is_running() is None
    assert "STOPPED" in daemon.status()


def test_start_stop_lifecycle(isolated_home, monkeypatch):
    # Replace the spawned command with a trivial long-lived sleeper so the test
    # exercises the PID/lifecycle without launching the whole stack.
    import subprocess

    real_popen = subprocess.Popen

    def fake_popen(cmd, **kwargs):
        return real_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    msg = daemon.start(interval=1)
    assert "started in background" in msg
    assert (isolated_home / "agent.pid").exists()

    # give the OS a moment to register the process
    for _ in range(20):
        if daemon.is_running():
            break
        time.sleep(0.05)
    assert daemon.is_running() is not None
    assert "RUNNING" in daemon.status()

    # starting again is a no-op while running
    assert "already running" in daemon.start(interval=1)

    out = daemon.stop()
    assert "stop signal sent" in out
    assert not (isolated_home / "agent.pid").exists()


def test_stop_when_not_running(isolated_home):
    assert "not running" in daemon.stop()
