"""Tests for the SaaS web layer (webapp/backend): signup, auth, quota
enforcement, billing fallback behavior, job lifecycle, and the frontend
being served. Requires the optional ``webapp`` extra (fastapi/stripe/httpx);
skipped automatically when it isn't installed.
"""

from __future__ import annotations

import importlib
from pathlib import Path
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


def test_update_profile_sets_display_name(client):
    key = _signup(client)
    res = client.patch("/api/me", headers={"X-API-Key": key}, json={"display_name": "  Ada  "})
    assert res.status_code == 200
    assert res.json()["display_name"] == "Ada"

    res = client.get("/api/me", headers={"X-API-Key": key})
    assert res.json()["display_name"] == "Ada"


def test_update_profile_clears_display_name_on_blank(client):
    key = _signup(client)
    client.patch("/api/me", headers={"X-API-Key": key}, json={"display_name": "Ada"})
    res = client.patch("/api/me", headers={"X-API-Key": key}, json={"display_name": "  "})
    assert res.status_code == 200
    assert res.json()["display_name"] is None


def test_update_profile_rejects_overly_long_name(client):
    key = _signup(client)
    res = client.patch("/api/me", headers={"X-API-Key": key}, json={"display_name": "x" * 81})
    assert res.status_code == 422


def test_regenerate_key_rotates_and_invalidates_old_key(client):
    old_key = _signup(client)
    res = client.post("/api/me/regenerate-key", headers={"X-API-Key": old_key})
    assert res.status_code == 200
    new_key = res.json()["api_key"]
    assert new_key != old_key

    assert client.get("/api/me", headers={"X-API-Key": old_key}).status_code == 401
    assert client.get("/api/me", headers={"X-API-Key": new_key}).status_code == 200


def test_watchlist_add_list_remove(client):
    key = _signup(client)
    headers = {"X-API-Key": key}

    res = client.post("/api/watchlist", headers=headers, json={"ticker": "nvda"})
    assert res.status_code == 200
    assert [row["ticker"] for row in res.json()] == ["NVDA"]

    res = client.post("/api/watchlist", headers=headers, json={"ticker": "nvda"})
    assert [row["ticker"] for row in res.json()] == ["NVDA"]  # idempotent, no dup

    client.post("/api/watchlist", headers=headers, json={"ticker": "TSLA"})
    res = client.get("/api/watchlist", headers=headers)
    assert sorted(row["ticker"] for row in res.json()) == ["NVDA", "TSLA"]

    res = client.delete("/api/watchlist/nvda", headers=headers)
    assert res.status_code == 200
    assert [row["ticker"] for row in res.json()] == ["TSLA"]


def test_job_history_filters_by_ticker_and_status(client):
    from webapp.backend import database

    key = _signup(client)
    user = database.get_user_by_api_key(key)
    database.create_job("j-nvda", user["id"], "NVDA", "2024-01-01")
    database.update_job("j-nvda", status="done", decision="BUY", finished_at="x")
    database.create_job("j-tsla", user["id"], "TSLA", "2024-01-01")
    database.update_job("j-tsla", status="failed", error="boom", finished_at="x")

    res = client.get("/api/jobs", headers={"X-API-Key": key}, params={"ticker": "nvda"})
    assert [j["id"] for j in res.json()] == ["j-nvda"]

    res = client.get("/api/jobs", headers={"X-API-Key": key}, params={"status": "failed"})
    assert [j["id"] for j in res.json()] == ["j-tsla"]


def test_chart_returns_price_series(client):
    import pandas as pd

    from webapp.backend import charts

    key = _signup(client)

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period):
            idx = pd.to_datetime(["2024-05-08", "2024-05-09", "2024-05-10"])
            return pd.DataFrame({"Close": [100.0, 101.5, 99.25]}, index=idx)

    with patch.object(charts.yf, "Ticker", FakeTicker):
        res = client.get("/api/chart/nvda", headers={"X-API-Key": key}, params={"range": "1mo"})

    assert res.status_code == 200
    body = res.json()
    assert body["ticker"] == "NVDA"
    assert body["range"] == "1mo"
    assert body["points"] == [
        {"date": "2024-05-08", "close": 100.0},
        {"date": "2024-05-09", "close": 101.5},
        {"date": "2024-05-10", "close": 99.25},
    ]


def test_chart_rejects_invalid_range(client):
    key = _signup(client)
    res = client.get("/api/chart/NVDA", headers={"X-API-Key": key}, params={"range": "not-a-range"})
    assert res.status_code == 422


def test_chart_502_when_ticker_has_no_data(client):
    from webapp.backend import charts

    key = _signup(client)

    class EmptyTicker:
        def __init__(self, symbol):
            pass

        def history(self, period):
            import pandas as pd

            return pd.DataFrame()

    with patch.object(charts.yf, "Ticker", EmptyTicker):
        res = client.get("/api/chart/ZZZZ", headers={"X-API-Key": key})

    assert res.status_code == 502


def test_me_defaults_to_usd(client):
    key = _signup(client)
    res = client.get("/api/me", headers={"X-API-Key": key})
    assert res.json()["currency"] == "USD"


def test_update_profile_sets_currency(client):
    key = _signup(client)
    res = client.patch("/api/me", headers={"X-API-Key": key}, json={"currency": "eur"})
    assert res.status_code == 200
    assert res.json()["currency"] == "EUR"

    res = client.get("/api/me", headers={"X-API-Key": key})
    assert res.json()["currency"] == "EUR"


def test_update_profile_rejects_unsupported_currency(client):
    key = _signup(client)
    res = client.patch("/api/me", headers={"X-API-Key": key}, json={"currency": "XYZ"})
    assert res.status_code == 422


def test_update_profile_currency_does_not_clobber_display_name(client):
    """A PATCH that only sends `currency` must not wipe an existing
    display_name (regression: the handler used to unconditionally rewrite
    display_name on every PATCH, defaulting it to null)."""
    key = _signup(client)
    client.patch("/api/me", headers={"X-API-Key": key}, json={"display_name": "Ada"})
    res = client.patch("/api/me", headers={"X-API-Key": key}, json={"currency": "GBP"})
    assert res.status_code == 200
    assert res.json()["display_name"] == "Ada"
    assert res.json()["currency"] == "GBP"


def test_rates_board_for_base_currency(client):
    import pandas as pd

    from webapp.backend import rates

    key = _signup(client)

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period):
            # Deterministic "rate" derived from the ticker symbol so each
            # currency pair gets a distinct, checkable value.
            value = 1.0 + (sum(ord(c) for c in self.symbol) % 10) / 10
            return pd.DataFrame({"Close": [value]}, index=pd.to_datetime(["2024-05-10"]))

    with patch.object(rates.yf, "Ticker", FakeTicker):
        res = client.get("/api/rates", headers={"X-API-Key": key}, params={"base": "usd"})

    assert res.status_code == 200
    body = res.json()
    assert body["base"] == "USD"
    assert body["rates"]["USD"] == 1.0
    assert set(body["rates"]) == set(rates.SUPPORTED_CURRENCIES)


def test_rates_rejects_unsupported_base(client):
    key = _signup(client)
    res = client.get("/api/rates", headers={"X-API-Key": key}, params={"base": "XYZ"})
    assert res.status_code == 422


def test_rates_502_when_unavailable(client):
    from webapp.backend import rates

    key = _signup(client)

    class BrokenTicker:
        def __init__(self, symbol):
            pass

        def history(self, period):
            raise RuntimeError("network down")

    with patch.object(rates.yf, "Ticker", BrokenTicker):
        res = client.get("/api/rates", headers={"X-API-Key": key}, params={"base": "USD"})

    assert res.status_code == 502


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


def _require_built_frontend():
    dist = Path(__file__).resolve().parents[1] / "webapp" / "frontend" / "dist"
    if not dist.is_dir():
        pytest.skip("webapp/frontend/dist not built — run `npm run build` in webapp/frontend")


def test_frontend_is_served(client):
    _require_built_frontend()
    res = client.get("/")
    assert res.status_code == 200
    assert "TradingAgents" in res.text


def test_frontend_spa_routes_serve_index_html(client):
    """A hard refresh or shared link to a client-side route (e.g. /history)
    must serve index.html so react-router can take over, not 404."""
    _require_built_frontend()
    for path in ("/history", "/watchlist", "/profile", "/some/deep/unknown/path"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert "TradingAgents" in res.text, path


def test_unmatched_api_path_still_404s_not_index_html(client):
    _require_built_frontend()
    res = client.get("/api/this-route-does-not-exist")
    assert res.status_code == 404
    assert "TradingAgents" not in res.text


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


def test_analyze_serves_cached_result_across_users(client):
    """A second user requesting the same (ticker, trade_date) gets the first
    user's completed result instantly, without spending LLM cost or quota."""
    from webapp.backend import database, jobs

    first_key = _signup(client, "first@example.com")
    first_user = database.get_user_by_api_key(first_key)
    database.create_job("done-job", first_user["id"], "NVDA", "2024-05-10")
    database.update_job(
        "done-job", status="done", decision="BUY", report="strong report",
        finished_at="2024-05-10T00:00:00+00:00",
    )

    second_key = _signup(client, "second@example.com")
    with patch.object(jobs, "_EXECUTOR") as mock_executor:
        res = client.post(
            "/api/analyze",
            headers={"X-API-Key": second_key},
            json={"ticker": "NVDA", "trade_date": "2024-05-10"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["cached"] is True
        assert body["status"] == "done"
        assert not mock_executor.submit.called

    job = client.get(f"/api/jobs/{body['job_id']}", headers={"X-API-Key": second_key}).json()
    assert job["decision"] == "BUY"
    assert job["report"] == "strong report"
    assert job["cached"] == 1

    # the cache hit must not count against the second user's monthly quota
    me = client.get("/api/me", headers={"X-API-Key": second_key}).json()
    assert me["jobs_this_month"] == 0


def test_analyze_cache_disabled_when_ttl_zero(client, monkeypatch):
    from webapp.backend import database, jobs

    monkeypatch.setenv("TRADINGAGENTS_CACHE_TTL_HOURS", "0")

    first_key = _signup(client, "third@example.com")
    first_user = database.get_user_by_api_key(first_key)
    database.create_job("done-job-2", first_user["id"], "NVDA", "2024-05-10")
    database.update_job("done-job-2", status="done", decision="BUY", report="r")

    second_key = _signup(client, "fourth@example.com")
    with patch.object(jobs, "_EXECUTOR") as mock_executor:
        res = client.post(
            "/api/analyze",
            headers={"X-API-Key": second_key},
            json={"ticker": "NVDA", "trade_date": "2024-05-10"},
        )
        assert res.status_code == 200
        assert res.json()["cached"] is False
        assert mock_executor.submit.called


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
