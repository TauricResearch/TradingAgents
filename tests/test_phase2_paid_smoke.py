"""Explicitly opt-in CIII-only and Yahoo + CIII acceptance flows."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

from tradingagents.persistence import Database, Repository
from tradingagents.usage import (
    BudgetExhaustedError,
    BudgetLimits,
    BudgetTracker,
    paid_tests_enabled,
)
from tradingagents.usage.budget import BudgetedRunnable

ENABLED, REASON = paid_tests_enabled()
pytestmark = [
    pytest.mark.paid,
    pytest.mark.integration,
    pytest.mark.skipif(not ENABLED, reason=REASON or "paid tests disabled"),
]

FIXED_EVIDENCE = (
    "Fixed evidence fixture. Instrument: TEST-FUND. Analysis date: 2026-07-22. "
    "Currency: USD. Cutoff price: 100.00. Freshness: fresh. "
    "Return exactly the word CONNECTED. Do not retrieve external data."
)


def test_paid_ciii_only_connectivity_usage_and_hard_budget(tmp_path):
    """One bounded CIII request with no Yahoo or other provider dependency."""
    from tradingagents.llm_clients import create_llm_client

    model = os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM")
    base_url = os.environ.get("TRADINGAGENTS_CIII_BASE_URL")
    if not model or not base_url or not os.environ.get("CIII_API_KEY"):
        pytest.skip("CIII endpoint, key, and quick model ID are required")

    configured = BudgetLimits.from_env()
    limits = replace(
        configured,
        max_requests_per_analysis=1,
        max_retries_per_request=0,
    )
    repository = Repository(Database(tmp_path / "ciii-only-smoke.sqlite3"))
    job = repository.create_job({"symbol": "TEST-FUND", "llm_provider": "ciii"})
    tracker = BudgetTracker(
        repository,
        job_id=job.id,
        provider="ciii",
        limits=limits,
    )
    llm = create_llm_client(
        "ciii",
        model,
        base_url=base_url,
        max_retries=0,
        timeout=30,
    ).get_llm()
    response = BudgetedRunnable(llm, tracker, model).invoke(FIXED_EVIDENCE)
    assert str(response.content).strip()

    summary = tracker.summary()
    assert summary["requests"] == 1
    assert summary["retries"] == 0
    assert summary["token_usage_complete"] is True
    assert 0 < summary["total_tokens"] <= configured.max_total_tokens_per_analysis
    with pytest.raises(BudgetExhaustedError, match="ANALYSIS_REQUEST_LIMIT"):
        tracker.before_request()


def test_paid_spy_analysis_fresh_chat_and_reevaluation(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from tradingagents.web.app import create_app

    quick = os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM")
    deep = os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM")
    if not quick or not deep or not os.environ.get("CIII_API_KEY") or not os.environ.get("TRADINGAGENTS_CIII_BASE_URL"):
        pytest.skip("CIII endpoint, key, and quick/deep model IDs are required")

    repository = Repository(Database(tmp_path / "paid-smoke.sqlite3"))
    app = create_app(demo=False, repository=repository)
    client = TestClient(app)
    created = client.post("/api/analyses", json={
        "symbol": "SPY", "asset_type": "fund", "analysis_date": "2026-07-22",
        "benchmark_symbol": "SPY", "analysts": ["market", "fundamentals"],
        "research_depth": 1, "llm_provider": "ciii", "quick_model": quick,
        "deep_model": deep, "output_language": "English",
    })
    assert created.status_code == 202
    job_id = created.json()["job_id"]
    app.state.jobs.threads[job_id].join(timeout=600)
    state = client.get(f"/api/analyses/{job_id}").json()
    assert state["status"] == "completed", state.get("error")
    usage = client.get(f"/api/analyses/{job_id}/usage").json()["summary"]
    assert 0 < usage["requests"] <= int(os.environ["TRADINGAGENTS_BUDGET_MAX_REQUESTS"])
    assert usage["total_tokens"] <= int(os.environ["TRADINGAGENTS_BUDGET_MAX_TOKENS"])

    conversation = client.post(
        f"/api/reports/{state['report_id']}/conversations"
    ).json()
    reply = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={
            "content": "Using current data, propose a candidate adjustment and explain conflicts.",
            "refresh_data": True,
            "candidate_adjustment": True,
        },
    ).json()
    child = client.post(
        f"/api/conversations/{conversation['id']}/re-evaluate",
        json={"trigger_message_ids": [reply["user"]["id"], reply["assistant"]["id"]]},
    )
    assert child.status_code == 201 and child.json()["version"] == 2
