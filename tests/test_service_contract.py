from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tradingagents_service.api.app import create_app
from tradingagents_service.api.dependencies import get_shadow_run_repository
from tradingagents_service.artifacts import LocalArtifactBackend
from tradingagents_service.db.repository import ShadowRunRepository
from tradingagents_service.schemas.shadow_runs import RunStatus
from tradingagents_service.ticker_validation import TickerValidationResult


class _StubRepo:
    def __init__(self) -> None:
        self.run_id = uuid4()
        self.last_create_kwargs = None
        self.last_list_kwargs = None
        self.last_precedent_lookup_kwargs = None
        self.existing_run = None

    async def create_queued_run(self, **kwargs):
        self.last_create_kwargs = kwargs
        if self.existing_run is not None:
            return self.existing_run
        return type(
            "Run",
            (),
            {
                "id": self.run_id,
                "status": type("S", (), {"value": "queued"})(),
                "ticker": kwargs["ticker"],
                "trade_date": kwargs["trade_date"],
                "selected_analysts": kwargs["selected_analysts"],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "provider": None,
                "model": None,
                "error_message": None,
                "metadata_json": kwargs.get("metadata_json"),
            },
        )()

    async def get_run_by_idempotency_key(self, idempotency_key):
        return self.existing_run

    async def get_run_by_id(self, run_id):
        if run_id != self.run_id:
            return None
        return type(
            "Run",
            (),
            {
                "id": self.run_id,
                "status": type("S", (), {"value": "queued"})(),
                "ticker": "NVDA",
                "trade_date": date(2026, 1, 15),
                "selected_analysts": ["market", "news"],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "provider": None,
                "model": None,
                "error_message": None,
                "metadata_json": {"target_profile": {"investor_type": "income", "horizon": "6m"}},
            },
        )()

    async def get_events_by_run_id(self, run_id):
        if run_id != self.run_id:
            return []
        evt = type(
            "E",
            (),
            {
                "id": uuid4(),
                "created_at": datetime.now(timezone.utc),
                "event_type": "queued",
                "payload": {"ok": True},
                "sequence": 1,
            },
        )()
        return [evt]

    async def get_artifacts_by_run_id(self, run_id):
        if run_id != self.run_id:
            return []
        art = type(
            "A",
            (),
            {
                "id": uuid4(),
                "artifact_type": "state_log",
                "path": "/tmp/x.json",
                "metadata_json": {"sha256": "abc", "content_type": "application/json", "bytes": 12},
            },
        )()
        return [art]

    async def get_output_by_run_id(self, run_id):
        if run_id != self.run_id:
            return None
        return type(
            "O",
            (),
            {
                "final_rating": "Hold",
                "decision_markdown": "decision",
                "state_log_dir": "/tmp/state",
                "memory_log_path": "/tmp/mem.md",
                "provider_metadata": {
                    "provider": "ollama",
                    "deep_model": "llama3.2:latest",
                    "quick_model": "llama3.2:latest",
                    "quality": {
                        "status": "warning",
                        "findings": [
                            {
                                "code": "no_explicit_source_reference",
                                "severity": "warning",
                                "message": "Final decision lacks explicit source references or URLs.",
                                "evidence": None,
                            }
                        ],
                        "source_summary": {"requested_ticker": "NVDA"},
                        "recommendation_audit": {
                            "final_rating": "Hold",
                            "alignment_status": "aligned",
                            "intermediate_report_count": 2,
                        },
                    },
                },
            },
        )()

    async def list_runs(self, **kwargs):
        self.last_list_kwargs = kwargs
        limit = kwargs.get("limit", 25)
        offset = kwargs.get("offset", 0)
        if offset > 0:
            return []
        return [
            type(
                "Run",
                (),
                {
                    "id": self.run_id,
                    "status": type("S", (), {"value": "queued"})(),
                    "ticker": "NVDA",
                    "trade_date": date(2026, 1, 15),
                    "selected_analysts": ["market", "news"],
                    "created_at": datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "error_message": None,
                    "metadata_json": {"target_profile": {"investor_type": "growth", "horizon": "12m"}},
                },
            )()
        ][:limit]

    async def search_precedents_for_run(self, **kwargs):
        self.last_precedent_lookup_kwargs = kwargs
        if kwargs.get("run_id") != self.run_id:
            return []
        precedent = type(
            "Precedent",
            (),
            {
                "run_id": uuid4(),
                "ticker": "NVDA",
                "trade_date": date(2026, 1, 10),
                "similarity": 0.91,
                "content_hash": "abc123",
                "content_text": "prior NVDA precedent",
                "embedding_model": "hashed-bow-v1",
                "metadata_json": {"final_rating": "Hold"},
                "created_at": datetime.now(timezone.utc),
            },
        )()
        return [precedent]

    async def search_precedents(self, **kwargs):
        self.last_precedent_lookup_kwargs = kwargs
        precedent = type(
            "Precedent",
            (),
            {
                "run_id": uuid4(),
                "ticker": kwargs.get("ticker") or "NVDA",
                "trade_date": kwargs.get("before_trade_date") or date(2026, 1, 10),
                "similarity": 0.84,
                "content_hash": "def456",
                "content_text": "collection search precedent",
                "embedding_model": "hashed-bow-v1",
                "metadata_json": {"final_rating": "Buy"},
                "created_at": datetime.now(timezone.utc),
            },
        )()
        return [precedent]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(
        "tradingagents_service.api.routes.shadow_runs.validate_ticker_for_shadow_run",
        lambda ticker: TickerValidationResult(accepted=True, symbol=ticker),
    )
    app = create_app()
    stub = _StubRepo()

    async def _repo_override():
        yield stub

    app.dependency_overrides[get_shadow_run_repository] = _repo_override
    with TestClient(app) as test_client:
        yield test_client, stub


@pytest.mark.unit
def test_create_run_validation_errors(client):
    test_client, _ = client
    resp = test_client.post("/v1/shadow-runs", json={})
    assert resp.status_code == 422


@pytest.mark.unit
def test_idempotency_key_deterministic():
    key1 = ShadowRunRepository.build_idempotency_key(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        selected_analysts=["news", "market"],
        provider="ollama",
        model="llama3.2:latest",
    )
    key2 = ShadowRunRepository.build_idempotency_key(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        selected_analysts=["market", "news"],
        provider="ollama",
        model="llama3.2:latest",
    )
    assert key1 == key2


@pytest.mark.unit
def test_create_run_returns_202_shape(client):
    test_client, stub = client
    payload = {
        "ticker": "NVDA",
        "trade_date": "2026-01-15",
        "selected_analysts": ["market", "news"],
        "target_profile": {"investor_type": "growth", "horizon": "12m", "risk_appetite": "moderate"},
    }
    resp = test_client.post("/v1/shadow-runs", json=payload)
    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"] == str(stub.run_id)
    assert body["status"] == RunStatus.queued.value
    assert body["reused_existing"] is False
    assert body["submission_kind"] == "queued"
    assert body["links"]["self"].endswith(str(stub.run_id))
    assert stub.last_create_kwargs["metadata_json"]["target_profile"]["investor_type"] == "growth"


@pytest.mark.unit
def test_create_run_rejects_invalid_ticker_before_queueing(client, monkeypatch):
    test_client, stub = client
    monkeypatch.setattr(
        "tradingagents_service.api.routes.shadow_runs.validate_ticker_for_shadow_run",
        lambda ticker: TickerValidationResult(
            accepted=False,
            symbol=ticker,
            reason="ticker APPL is a likely typo",
            suggestion="AAPL",
        ),
    )
    payload = {
        "ticker": "APPL",
        "trade_date": "2026-05-05",
        "selected_analysts": ["market", "news"],
    }

    resp = test_client.post("/v1/shadow-runs", json=payload)

    assert resp.status_code == 422
    assert "Did you mean 'AAPL'" in resp.json()["detail"]
    assert stub.last_create_kwargs is None


@pytest.mark.unit
def test_create_run_marks_matching_existing_run_as_retrieval(client):
    test_client, stub = client
    stub.existing_run = type(
        "Run",
        (),
        {
            "id": stub.run_id,
            "status": type("S", (), {"value": "succeeded"})(),
            "ticker": "NVDA",
            "trade_date": date(2026, 1, 15),
            "selected_analysts": ["market", "news"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "provider": None,
            "model": None,
            "error_message": None,
            "metadata_json": {"target_profile": {"investor_type": "growth", "horizon": "12m"}},
        },
    )()
    payload = {
        "ticker": "NVDA",
        "trade_date": "2026-01-15",
        "selected_analysts": ["market", "news"],
    }

    resp = test_client.post("/v1/shadow-runs", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == str(stub.run_id)
    assert body["status"] == RunStatus.succeeded.value
    assert body["reused_existing"] is True
    assert body["submission_kind"] == "retrieved"
    assert body["links"]["self"].endswith(str(stub.run_id))


@pytest.mark.unit
def test_create_run_passes_provider_model_into_idempotency_and_queue_payload(client):
    test_client, stub = client
    payload = {
        "ticker": "NVDA",
        "trade_date": "2026-01-15",
        "selected_analysts": ["market", "news"],
        "provider": "openai",
        "model": "gpt-4.1",
    }
    resp = test_client.post("/v1/shadow-runs", json=payload)
    assert resp.status_code == 202

    expected_key = ShadowRunRepository.build_idempotency_key(
        ticker="NVDA",
        trade_date=date(2026, 1, 15),
        selected_analysts=["market", "news"],
        provider="openai",
        model="gpt-4.1",
    )
    assert stub.last_create_kwargs["provider"] == "openai"
    assert stub.last_create_kwargs["model"] == "gpt-4.1"
    assert stub.last_create_kwargs["idempotency_key"] == expected_key


@pytest.mark.unit
def test_get_run_with_unknown_analyst_value_does_not_500(client):
    test_client, stub = client
    original_get = stub.get_run_by_id

    async def _unknown_analyst_run(run_id):
        run = await original_get(run_id)
        if run is None:
            return None
        run.selected_analysts = ["market", "experimental_analyst"]
        return run

    stub.get_run_by_id = _unknown_analyst_run
    resp = test_client.get(f"/v1/shadow-runs/{stub.run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["selected_analysts"] == ["market", "experimental_analyst"]


@pytest.mark.unit
def test_shadow_run_read_paths_surface_target_profile(client):
    test_client, stub = client

    resp = test_client.get(f"/v1/shadow-runs/{stub.run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_profile"]["investor_type"] == "income"

    handoff = test_client.get(f"/v1/shadow-runs/{stub.run_id}/handoff")
    assert handoff.status_code == 200
    handoff_body = handoff.json()
    assert handoff_body["target_profile"]["investor_type"] == "income"


@pytest.mark.unit
def test_artifact_hash_deterministic(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("same-bytes", encoding="utf-8")
    backend = LocalArtifactBackend()
    a = backend.manifest_entry_for_file(kind="test", path=p, content_type="text/plain")
    b = backend.manifest_entry_for_file(kind="test", path=p, content_type="text/plain")
    assert a.sha256 == b.sha256
    assert a.bytes == b.bytes


@pytest.mark.unit
def test_run_related_endpoints(client):
    test_client, stub = client
    rid = str(stub.run_id)
    assert test_client.get(f"/v1/shadow-runs/{rid}").status_code == 200
    assert test_client.get(f"/v1/shadow-runs/{rid}/events").status_code == 200
    assert test_client.get(f"/v1/shadow-runs/{rid}/artifacts").status_code == 200
    decision = test_client.get(f"/v1/shadow-runs/{rid}/decision")
    assert decision.status_code == 200
    body = decision.json()
    assert body["final_rating"] == "invalid_due_to_quality_gate"
    assert body["recommendation_status"] == "invalid"
    assert body["invalidated_by_quality_gate"] is True
    assert body["original_final_rating"] == "Hold"
    assert body["quality_status"] == "warning"
    assert body["quality_findings"][0]["code"] == "no_explicit_source_reference"
    assert body["invalidating_findings"][0]["code"] == "no_explicit_source_reference"
    assert body["recommendation_audit"]["alignment_status"] == "aligned"
    assert body["target_profile"]["investor_type"] == "income"


@pytest.mark.unit
def test_list_runs_returns_expected_shape(client):
    test_client, stub = client
    resp = test_client.get("/v1/shadow-runs?limit=10&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert "runs" in body
    assert isinstance(body["runs"], list)
    assert len(body["runs"]) == 1
    run = body["runs"][0]
    assert run["run_id"] == str(stub.run_id)
    assert run["ticker"] == "NVDA"
    assert run["trade_date"] == "2026-01-15"
    assert run["status"] == RunStatus.queued.value


@pytest.mark.unit
def test_list_runs_accepts_exact_ticker_date_lookup(client):
    test_client, stub = client
    resp = test_client.get("/v1/shadow-runs?ticker=NVDA&date_from=2026-01-15&date_to=2026-01-15&limit=10")

    assert resp.status_code == 200
    assert stub.last_list_kwargs["ticker"] == "NVDA"
    assert stub.last_list_kwargs["date_from"] == date(2026, 1, 15)
    assert stub.last_list_kwargs["date_to"] == date(2026, 1, 15)
    assert stub.last_list_kwargs["limit"] == 10


@pytest.mark.unit
def test_handoff_payload_shape(client):
    test_client, stub = client
    resp = test_client.get(f"/v1/shadow-runs/{stub.run_id}/handoff")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["run_id"] == str(stub.run_id)
    assert payload["ticker"] == "NVDA"
    assert payload["trade_date"] == "2026-01-15"
    assert payload["final_rating"] == "invalid_due_to_quality_gate"
    assert payload["final_decision_markdown"].startswith("# Recommendation invalidated by quality gate")
    assert payload["recommendation_status"] == "invalid"
    assert payload["invalidated_by_quality_gate"] is True
    assert payload["original_final_rating"] == "Hold"
    assert payload["state_log_dir"] == "/tmp/state"
    assert payload["memory_log_path"] == "/tmp/mem.md"
    assert payload["provider"] == "ollama"
    assert payload["deep_model"] == "llama3.2:latest"
    assert payload["quick_model"] == "llama3.2:latest"
    assert payload["quality_status"] == "warning"
    assert payload["source_summary"] == {"requested_ticker": "NVDA"}
    assert payload["recommendation_audit"]["final_rating"] == "Hold"
    assert payload["target_profile"]["investor_type"] == "income"
    assert payload["precedent_summary"]["precedent_count"] == 1


@pytest.mark.unit
def test_precedent_lookup_endpoint_returns_nearest_runs(client):
    test_client, stub = client
    resp = test_client.get(f"/v1/shadow-runs/{stub.run_id}/precedents?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["query_run_id"] == str(stub.run_id)
    assert body["query_ticker"] == "NVDA"
    assert body["precedents"][0]["content_hash"] == "abc123"
    assert stub.last_precedent_lookup_kwargs["limit"] == 5


@pytest.mark.unit
def test_collection_precedent_lookup_endpoint_returns_results(client):
    test_client, stub = client
    resp = test_client.get("/v1/precedents?ticker=NVDA&trade_date=2026-01-15&query_text=margin")
    assert resp.status_code == 200
    body = resp.json()
    assert body["query_ticker"] == "NVDA"
    assert body["precedents"][0]["content_hash"] == "def456"


@pytest.mark.unit
def test_report_markdown_saved_after_completion(client):
    test_client, stub = client
    original_get = stub.get_run_by_id

    async def _completed_run(run_id):
        run = await original_get(run_id)
        if run is None:
            return None
        run.status = type("S", (), {"value": "succeeded"})()
        return run

    stub.get_run_by_id = _completed_run

    resp = test_client.get(f"/v1/shadow-runs/{stub.run_id}/report.md")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert resp.headers["x-report-path"].endswith(f"{stub.run_id}.md")
    assert f"# TradingAgents Shadow Run Report: NVDA 2026-01-15" in resp.text
    assert "## Quality Gate" in resp.text
    assert "## Runtime Timeline" in resp.text


@pytest.mark.unit
def test_root_route_returns_html():
    app = create_app()
    with TestClient(app) as test_client:
        resp = test_client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "<!doctype html>" in resp.text.lower()
