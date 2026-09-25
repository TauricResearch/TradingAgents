"""Tests for the SaaS web layer (webapp/backend): signup, auth, quota
enforcement, billing fallback behavior, job lifecycle, and the frontend
being served. Requires the optional ``webapp`` extra (fastapi/stripe/httpx);
skipped automatically when it isn't installed.
"""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient wired to a throwaway sqlite file per test."""
    monkeypatch.setenv("TRADINGAGENTS_WEBAPP_DB", str(tmp_path / "webapp.sqlite3"))
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)

    # database/billing read config at call time, but re-import main/billing so
    # any module-level state (e.g. billing.STRIPE_SECRET_KEY) picks up the
    # patched environment for this test.
    from webapp.backend import billing, database, jobs, main

    importlib.reload(billing)
    importlib.reload(database)
    importlib.reload(jobs)
    importlib.reload(main)

    with TestClient(main.app) as c:
        yield c


def _signup(client, email="user@example.com") -> str:
    res = client.post("/api/signup", json={"email": email})
    assert res.status_code == 200, res.text
    return res.json()["api_key"]


def test_signup_returns_api_key(client):
    res = client.post("/api/signup", json={"email": "new@example.com"})
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "new@example.com"
    assert body["api_key"].startswith("ta_")
    assert body["plan"] == "free"


def test_signup_duplicate_email_rejected(client):
    _signup(client, "dup@example.com")
    res = client.post("/api/signup", json={"email": "dup@example.com"})
    assert res.status_code == 409


def test_me_reports_plan_and_usage(client):
    key = _signup(client)
    res = client.get("/api/me", headers={"X-API-Key": key})
    assert res.status_code == 200
    body = res.json()
    assert body["plan"] == "free"
    assert body["jobs_this_month"] == 0
    assert body["free_tier_limit"] == 5


def test_missing_api_key_rejected(client):
    res = client.get("/api/me")
    assert res.status_code == 422  # missing required header


def test_invalid_api_key_rejected(client):
    res = client.get("/api/me", headers={"X-API-Key": "not-a-real-key"})
    assert res.status_code == 401


def test_job_history_empty_for_new_user(client):
    key = _signup(client)
    res = client.get("/api/jobs", headers={"X-API-Key": key})
    assert res.status_code == 200
    assert res.json() == []


def test_unknown_job_id_404s(client):
    key = _signup(client)
    res = client.get("/api/jobs/does-not-exist", headers={"X-API-Key": key})
    assert res.status_code == 404


def test_billing_checkout_503_when_unconfigured(client):
    key = _signup(client)
    res = client.post("/api/billing/checkout", headers={"X-API-Key": key})
    assert res.status_code == 503


def test_billing_webhook_503_when_unconfigured(client):
    res = client.post("/api/billing/webhook", content=b"{}")
    assert res.status_code == 503


def test_frontend_is_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "TradingAgents" in res.text


def test_analyze_enforces_free_tier_quota(client):
    from webapp.backend import database

    key = _signup(client)
    user = database.get_user_by_api_key(key)
    for i in range(database.free_tier_monthly_limit()):
        database.create_job(f"fake-{i}", user["id"], "NVDA", "2024-01-01")

    res = client.post("/api/analyze", headers={"X-API-Key": key}, json={"ticker": "NVDA"})
    assert res.status_code == 402


def test_analyze_pro_plan_bypasses_quota(client):
    from webapp.backend import database, jobs

    key = _signup(client)
    user = database.get_user_by_api_key(key)
    for i in range(database.free_tier_monthly_limit()):
        database.create_job(f"fake-{i}", user["id"], "NVDA", "2024-01-01")
    database.set_user_plan(user["id"], plan="pro")

    with patch.object(jobs, "_EXECUTOR") as mock_executor:
        res = client.post("/api/analyze", headers={"X-API-Key": key}, json={"ticker": "NVDA"})
        assert res.status_code == 200
        assert mock_executor.submit.called


def test_analyze_submits_job_and_tracks_status(client):
    from webapp.backend import jobs

    key = _signup(client)
    with patch.object(jobs, "_EXECUTOR") as mock_executor:
        res = client.post(
            "/api/analyze", headers={"X-API-Key": key}, json={"ticker": "nvda"}
        )
        assert res.status_code == 200
        job_id = res.json()["job_id"]
        assert res.json()["status"] == "queued"
        assert mock_executor.submit.called
        # ticker is normalized to uppercase before being queued
        _, submitted_ticker, _ = mock_executor.submit.call_args.args[1:]
        assert submitted_ticker == "NVDA"

    res = client.get(f"/api/jobs/{job_id}", headers={"X-API-Key": key})
    assert res.status_code == 200
    assert res.json()["status"] == "queued"


def test_run_job_records_success(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_WEBAPP_DB", str(tmp_path / "webapp.sqlite3"))
    from webapp.backend import database, jobs

    importlib.reload(database)
    importlib.reload(jobs)
    database.init_db()
    user = database.create_user("job@example.com")
    database.create_job("job-1", user["id"], "NVDA", "2024-05-10")

    fake_final_state = {"final_trade_decision": "BUY — strong fundamentals"}
    with patch.object(jobs, "TradingAgentsGraph") as MockGraph:
        MockGraph.return_value.propagate.return_value = (fake_final_state, "BUY")
        jobs._run_job("job-1", "NVDA", "2024-05-10")

    job = database.get_job("job-1", user["id"])
    assert job["status"] == "done"
    assert job["decision"] == "BUY"
    assert job["report"] == "BUY — strong fundamentals"
    assert job["finished_at"] is not None


def test_run_job_records_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_WEBAPP_DB", str(tmp_path / "webapp.sqlite3"))
    from webapp.backend import database, jobs

    importlib.reload(database)
    importlib.reload(jobs)
    database.init_db()
    user = database.create_user("fail@example.com")
    database.create_job("job-2", user["id"], "NVDA", "2024-05-10")

    with patch.object(jobs, "TradingAgentsGraph") as MockGraph:
        MockGraph.side_effect = ValueError("API key for provider 'openai' is not set")
        jobs._run_job("job-2", "NVDA", "2024-05-10")

    job = database.get_job("job-2", user["id"])
    assert job["status"] == "failed"
    assert "API key" in job["error"]
