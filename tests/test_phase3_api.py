from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from tradingagents.persistence import Database, Repository
from tradingagents.web.app import create_app


@pytest.fixture
def client(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    return TestClient(create_app(demo=True, repository=repository))


def test_search_resolve_snapshot_trust_and_sources(client):
    search = client.get("/api/funds/search", params={"q": "纳斯达克100"}).json()
    assert len(search["items"]) >= 3
    ambiguous = client.post("/api/funds/resolve", json={"query": "纳斯达克100"})
    assert ambiguous.status_code == 409
    assert ambiguous.json()["detail"]["code"] == "IDENTITY_AMBIGUOUS"

    identity = client.post("/api/funds/resolve", json={"query": "003516"}).json()
    assert identity["code"] == "003516" and identity["share_class"] == "A"
    snapshot = client.get(
        "/api/funds/003516/snapshot", params={"analysis_date": date.today().isoformat()}
    ).json()
    assert snapshot["nav_history"] and snapshot["trust"]["critical_ready"] is True
    assert client.get("/api/funds/003516/trust").json()["level"] == "trusted"
    assert client.get("/api/funds/003516/sources").json()["items"]


def test_evaluate_persists_only_executable_formal_advice(client):
    blocked = client.post(
        "/api/funds/003516/evaluate", json={"intended_action": "subscribe"}
    ).json()
    assert blocked["evaluation"]["executable"] is False
    assert blocked["formal_advice"] is None

    first = client.post(
        "/api/funds/003516/evaluate",
        json={"intended_action": "subscribe", "amount": "1000"},
    ).json()
    assert first["evaluation"]["executable"] is True
    assert first["evaluation"]["supporting_evidence"]
    assert first["evaluation"]["friction"]
    assert first["formal_advice"]["version"] == 1
    second = client.post("/api/funds/003516/evaluate", json={"intended_action": "hold"}).json()
    assert second["formal_advice"]["parent_id"] == first["formal_advice"]["id"]


def test_conversion_check_requires_explicit_platform_confirmation(client):
    blocked = client.post(
        "/api/funds/012920/conversion-check",
        json={
            "target_code": "012922",
            "sales_platform": "fixture",
            "conversion_supported": False,
        },
    ).json()
    assert not blocked["executable"]
    assert "PLATFORM_CONVERSION_UNCONFIRMED" in blocked["blocked_reasons"]
    allowed = client.post(
        "/api/funds/012920/conversion-check",
        json={
            "target_code": "012922",
            "sales_platform": "fixture",
            "conversion_supported": True,
            "confirmed_units": "100",
            "holding_days": 90,
            "minimum_holding_known": True,
        },
    ).json()
    assert allowed["executable"]


def test_six_digit_analysis_uses_china_fund_preflight_without_yahoo(client):
    created = client.post(
        "/api/analyses",
        json={
            "symbol": "016453",
            "asset_type": "auto",
            "analysis_date": date.today().isoformat(),
            "benchmark_symbol": "SPY",
            "analysts": ["market", "fundamentals"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "demo",
            "deep_model": "demo",
            "output_language": "Chinese",
        },
    )
    assert created.status_code == 202
    job_id = created.json()["job_id"]
    client.app.state.jobs.threads[job_id].join(timeout=3)
    job = client.get(f"/api/analyses/{job_id}").json()
    assert job["status"] == "completed"
    assert job["result"]["china_fund_snapshot"]["identity"]["code"] == "016453"
    assert job["result"]["fund_snapshot"]["instrument"]["currency"] == "CNY"
    trust = client.get(f"/api/analyses/{job_id}/trust").json()
    assert trust["evidence"] and trust["executable"] is True
