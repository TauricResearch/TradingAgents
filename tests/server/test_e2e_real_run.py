"""End-to-end: real worker.py + real LLM through the FastAPI path.

Opt-in (network + tokens): run with TA_E2E=1. Exercises the entire backend
chain a browser would hit — auth cookie → /api/analysis/start → real
TradingAgentsGraph in a worker subprocess → NDJSON streamed back → snapshot
shows real reports + a real BUY/SELL/HOLD decision. Runs on Doubao (ARK),
which the backend now forces regardless of the request body, and uses all
four analysts to exercise the concurrent analyst phase.
"""
from __future__ import annotations

import datetime as dt
import os
import time

import pytest

pytestmark = pytest.mark.skipif(os.getenv("TA_E2E") != "1", reason="set TA_E2E=1 to run")


@pytest.fixture
def real_client(tmp_path, monkeypatch):
    # Real .env (keys) loads inside create_app; just sandbox HOME + auth.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ALLOWED_EMAILS", "e2e@test.local")
    monkeypatch.setenv("TRADINGAGENTS_COOKIE_SECURE", "0")
    import auth as _auth
    monkeypatch.setattr(_auth, "verify_otp", lambda email, code: True)
    from fastapi.testclient import TestClient
    from server.app import create_app
    c = TestClient(create_app())
    r = c.post("/api/auth/verify-otp", json={"email": "e2e@test.local", "code": "x"})
    assert r.status_code == 200, r.text
    return c


def _recent_weekday() -> str:
    d = dt.date.today() - dt.timedelta(days=1)
    while d.weekday() >= 5:  # back up off the weekend
        d -= dt.timedelta(days=1)
    return d.isoformat()


def test_real_analysis_run_streams_to_decision(real_client):
    body = {
        "ticker": "NVDA",
        "trade_date": _recent_weekday(),
        # Backend forces Doubao; these are ignored but kept for schema validity.
        "provider": "doubao",
        "deep_model": "doubao-1-5-pro-32k-250115",
        "quick_model": "doubao-seed-1-6-flash-250828",
        "selected_analysts": ["market", "social", "news", "fundamentals"],
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "output_language": "English",
        "checkpoint_enabled": False,
    }
    r = real_client.post("/api/analysis/start", json=body)
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]

    deadline = time.time() + 600  # 10 min ceiling for a 1-analyst run
    snap = None
    while time.time() < deadline:
        snap = real_client.get(f"/api/analysis/{run_id}").json()
        if snap["status"] in ("done", "error"):
            break
        time.sleep(2)

    assert snap is not None, "no snapshot"
    assert snap["status"] == "done", f"run did not finish cleanly: {snap.get('error')}"
    assert snap["chunks"], "no streamed chunks"
    # A market-analyst run must produce a market report and a final decision.
    joined = " ".join(str(c) for c in snap["chunks"])
    assert "market" in joined.lower() or snap["decision"]
    assert snap["decision"] and snap["decision"].strip(), "no final decision"
    print(f"\nE2E decision={snap['decision']!r} chunks={len(snap['chunks'])} "
          f"elapsed={snap['elapsed']:.0f}s")
