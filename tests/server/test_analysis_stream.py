"""Analysis streaming core, driven by a stub worker (no real LLM)."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

STUB = str(Path(__file__).parent / "_stub_worker.py")


@pytest.fixture
def stub_env(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_WORKER_PATH", STUB)
    # Force the registry's settings to see the stub path.
    import server.config as cfg
    monkeypatch.setattr(cfg.settings, "worker_path", STUB, raising=False)


def _start(client):
    body = {
        "ticker": "TEST", "trade_date": "2026-06-09", "provider": "doubao",
        "deep_model": "d", "quick_model": "q", "selected_analysts": ["market"],
    }
    r = client.post("/api/analysis/start", json=body)
    assert r.status_code == 200, r.text
    return r.json()["run_id"]


def test_start_and_snapshot_reaches_done(auth_client, stub_env):
    run_id = _start(auth_client)
    deadline = time.time() + 15
    snap = None
    while time.time() < deadline:
        snap = auth_client.get(f"/api/analysis/{run_id}").json()
        if snap["status"] in ("done", "error"):
            break
        time.sleep(0.2)
    assert snap is not None and snap["status"] == "done", snap
    assert snap["decision"] == "BUY"
    assert len(snap["chunks"]) == 2
    assert snap["stats"]["llm_calls"] == 3


def test_sse_stream_emits_done(auth_client, stub_env):
    run_id = _start(auth_client)
    body = b""
    with auth_client.stream("GET", f"/api/analysis/{run_id}/stream") as resp:
        assert resp.status_code == 200
        for chunk in resp.iter_bytes():
            body += chunk
            if b"event: done" in body:
                break
    text = body.decode("utf-8")
    assert "event: started" in text
    assert "event: chunk" in text
    assert "event: done" in text


def test_snapshot_404_for_other_user(auth_client, stub_env):
    assert auth_client.get("/api/analysis/nonexistent").status_code == 404
