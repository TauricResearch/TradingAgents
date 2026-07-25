from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from tradingagents.dataflows.errors import ProviderRateLimitedError, ProviderTimedOutError
from tradingagents.persistence import Database, Repository
from tradingagents.services.analysis_service import DemoAnalysisService
from tradingagents.web.app import create_app
from tradingagents.web.jobs import JobManager


def payload(**overrides):
    value = {
        "symbol": "SPY", "asset_type": "auto", "analysis_date": "2026-07-21",
        "benchmark_symbol": "SPY", "analysts": ["market", "social", "news", "fundamentals"],
        "research_depth": 1, "llm_provider": "openai", "quick_model": "demo",
        "deep_model": "demo", "output_language": "English",
    }
    value.update(overrides)
    return value


def complete(client):
    job_id = client.post("/api/analyses", json=payload()).json()["job_id"]
    client.app.state.jobs.threads[job_id].join(timeout=2)
    value = client.get(f"/api/analyses/{job_id}").json()
    assert value["status"] == "completed"
    return job_id, value


def test_phase_two_api_survives_app_recreation_and_supports_chat_versions_backup(tmp_path):
    repository = Repository(Database(tmp_path / "state" / "workspace.sqlite3"))
    first_manager = JobManager(DemoAnalysisService(delay=0), repository=repository)
    first = TestClient(create_app(demo=True, manager=first_manager))
    job_id, completed = complete(first)
    report_id, first_advice_id = completed["report_id"], completed["advice_id"]
    original_events = first.get(f"/api/analyses/{job_id}/events").text
    assert "analysis.completed" in original_events

    restarted_manager = JobManager(DemoAnalysisService(delay=0), repository=repository)
    client = TestClient(create_app(demo=True, manager=restarted_manager))
    history = client.get("/api/analyses").json()["items"]
    assert history[0]["job_id"] == job_id and history[0]["status"] == "completed"
    assert client.get(f"/api/analyses/{job_id}/report.md").status_code == 200
    trust = client.get(f"/api/analyses/{job_id}/trust").json()
    assert trust["level"] == "trusted" and trust["evidence"]
    usage = client.get(f"/api/analyses/{job_id}/usage").json()
    assert usage["summary"]["requests"] == 0
    replay = client.get(f"/api/analyses/{job_id}/events?last_event_id=1").text
    assert "id: 1\n" not in replay and "analysis.completed" in replay

    conversation = client.post(f"/api/reports/{report_id}/conversations").json()
    reply = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "Candidate adjustment: sell if risk rises", "refresh_data": True, "candidate_adjustment": True},
    ).json()
    assert reply["assistant"]["refreshed_data"] is True
    assert reply["assistant"]["source_references"]
    versions_before = client.get(f"/api/reports/{report_id}/versions").json()["items"]
    assert [item["id"] for item in versions_before] == [first_advice_id]
    child = client.post(
        f"/api/conversations/{conversation['id']}/re-evaluate",
        json={"trigger_message_ids": [reply["user"]["id"], reply["assistant"]["id"]]},
    ).json()
    assert child["parent_id"] == first_advice_id and child["version"] == 2

    backup = client.post("/api/admin/backup").json()
    assert backup["valid"] and backup["compatible"] and "path" not in backup
    preview = client.post("/api/admin/restore/preview", json={"backup_id": backup["backup_id"]}).json()
    assert preview["schema_version"] == 4
    assert client.post("/api/admin/restore/commit", json={"backup_id": backup["backup_id"]}).json()["restored"] is True

    persisted_chat = client.get(f"/api/conversations/{conversation['id']}").json()
    assert len(persisted_chat["messages"]) == 2
    assert len(client.get(f"/api/reports/{report_id}/versions").json()["items"]) == 2
    serialized = json.dumps({"history": history, "trust": trust, "backup": backup}).lower()
    assert "api_key" not in serialized and str(tmp_path).lower() not in serialized


def test_api_exposes_interrupted_non_resumable_state(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    stale = repository.create_job(payload())
    repository.update_job(stale.id, "running")
    client = TestClient(create_app(
        demo=True,
        manager=JobManager(DemoAnalysisService(delay=0), repository=repository),
    ))
    state = client.get(f"/api/analyses/{stale.id}").json()
    assert state["status"] == "interrupted" and state["resumable"] is False
    rejected = client.post(f"/api/analyses/{stale.id}/resume")
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "JOB_NOT_RESUMABLE"


def test_budget_preflight_is_safe_and_depth_limit_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_BUDGET_MAX_DEBATE_ROUNDS", "1")
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    client = TestClient(create_app(demo=True, repository=repository))
    options = client.get("/api/config/options").json()
    assert options["budget"]["monetary_estimate"] == "unknown"
    assert options["budget"]["limits"]["max_debate_rounds"] == 1
    rejected = client.post("/api/analyses", json=payload(research_depth=2))
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "MAX_DEBATE_ROUNDS_EXCEEDED"


def test_provider_rate_limit_is_a_persisted_terminal_api_state_with_explicit_retry(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    attempts = 0

    def preflight(_job, value):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ProviderRateLimitedError("yahoo_finance", cache_status="expired")
        return value

    manager = JobManager(DemoAnalysisService(delay=0), repository=repository, preflight=preflight)
    client = TestClient(create_app(demo=True, manager=manager))
    created = client.post("/api/analyses", json=payload())
    assert created.status_code == 202
    parent_id = created.json()["job_id"]
    manager.threads[parent_id].join(timeout=2)

    state = client.get(f"/api/analyses/{parent_id}").json()
    assert state["status"] == "provider_rate_limited"
    assert state["error"]["cache_status"] == "expired"
    assert client.get(f"/api/analyses/{parent_id}/report.md").json()["detail"]["code"] == "PROVIDER_RATE_LIMITED"
    events = client.get(f"/api/analyses/{parent_id}/events").text
    assert "analysis.provider_rate_limited" in events
    usage = client.get(f"/api/analyses/{parent_id}/usage").json()["summary"]
    assert (usage["requests"], usage["total_tokens"], usage["retries"]) == (0, 0, 0)

    retried = client.post(f"/api/analyses/{parent_id}/retry")
    assert retried.status_code == 202
    child_id = retried.json()["job_id"]
    manager.threads[child_id].join(timeout=2)
    child = client.get(f"/api/analyses/{child_id}").json()
    assert child["retry_of_job_id"] == parent_id and child["retry_attempt"] == 1
    assert client.post(f"/api/analyses/{child_id}/retry").status_code == 409


def test_provider_timeout_is_persisted_and_retryable_without_ciii_usage(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    attempts = 0

    def preflight(_job, value):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ProviderTimedOutError(
                "yahoo_finance",
                timeout_seconds=6,
                cache_status="expired",
            )
        return value

    manager = JobManager(DemoAnalysisService(delay=0), repository=repository, preflight=preflight)
    client = TestClient(create_app(demo=True, manager=manager))
    parent_id = client.post("/api/analyses", json=payload()).json()["job_id"]
    manager.threads[parent_id].join(timeout=2)

    state = client.get(f"/api/analyses/{parent_id}").json()
    assert state["status"] == "provider_timed_out"
    assert state["error"]["code"] == "PROVIDER_TIMED_OUT"
    assert state["error"]["timeout_seconds"] == 6
    assert client.get(f"/api/analyses/{parent_id}/report.md").status_code == 409
    assert "analysis.provider_timed_out" in client.get(f"/api/analyses/{parent_id}/events").text
    usage = client.get(f"/api/analyses/{parent_id}/usage").json()["summary"]
    assert (usage["requests"], usage["total_tokens"], usage["retries"]) == (0, 0, 0)

    retried = client.post(f"/api/analyses/{parent_id}/retry")
    assert retried.status_code == 202
    child_id = retried.json()["job_id"]
    manager.threads[child_id].join(timeout=2)
    child = client.get(f"/api/analyses/{child_id}").json()
    assert child["status"] == "completed"
    assert child["retry_of_job_id"] == parent_id
