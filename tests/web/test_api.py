"""HTTP boundary contracts for the localhost TradingAgents workbench."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from tradingagents.execution.models import AnalysisRequest
from tradingagents.observability.events import RunEventDraft
from tradingagents.web.broker import EventBroker
from tradingagents.web.manager import (
    ActiveRunConflict,
    ResumeRunConflict,
    RunNotActive,
    RunNotResumable,
    RunNotRetryable,
)
from tradingagents.web.reports import ReportArtifactWriter
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import RunStore

pytestmark = pytest.mark.unit


VALID_RUN_BODY = {
    "ticker": "AAPL",
    "analysis_date": "2026-07-18",
    "asset_type": "stock",
    "selected_analysts": ["market", "fundamentals"],
    "research_depth": 1,
    "output_language": "Chinese",
    "llm_provider": "openai",
    "quick_think_llm": "gpt-5.4-mini",
    "deep_think_llm": "gpt-5.5",
    "checkpoint_enabled": False,
}


def _create_app(**kwargs: Any):
    # Keeping the import local makes collection fail with one clear missing-story
    # error until Story E3 adds the FastAPI boundary.
    from tradingagents.web.api import create_app

    return create_app(**kwargs)


def _snapshot(
    *,
    ticker: str = "AAPL",
    status: str = "running",
    run_id: str | None = None,
    **changes: Any,
) -> RunSnapshot:
    snapshot = RunSnapshot.create(
        run_id=run_id,
        ticker=ticker,
        analysis_date="2026-07-18",
        selected_analysts=("market", "fundamentals"),
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        output_language="Chinese",
        llm_provider="openai",
        quick_think_llm="gpt-5.4-mini",
        deep_think_llm="gpt-5.5",
        configured_keys={"openai": True},
    )
    return snapshot.evolve(status=status, **changes)


class RecordingManager:
    """Small manager double: the API must validate before calling it."""

    def __init__(self, store: RunStore) -> None:
        self.store = store
        self.calls: list[tuple[str, Any]] = []
        self.errors: dict[str, BaseException] = {}
        self.active_run_id: str | None = None

    def _raise(self, operation: str) -> None:
        error = self.errors.get(operation)
        if error is not None:
            raise error

    def start(
        self,
        request: AnalysisRequest,
        *,
        configured_keys: dict[str, bool] | None = None,
    ) -> RunSnapshot:
        self.calls.append(("start", (request, configured_keys)))
        self._raise("start")
        snapshot = RunSnapshot.create(
            ticker=request.ticker,
            analysis_date=request.analysis_date,
            asset_type=request.asset_type,
            selected_analysts=request.selected_analysts,
            max_debate_rounds=request.max_debate_rounds,
            max_risk_discuss_rounds=request.max_risk_discuss_rounds,
            output_language=str(request.effective_config["output_language"]),
            llm_provider=str(request.effective_config["llm_provider"]),
            quick_think_llm=str(request.effective_config["quick_think_llm"]),
            deep_think_llm=str(request.effective_config["deep_think_llm"]),
            configured_keys=configured_keys or {},
            metadata={"effective_config": dict(request.effective_config)},
        ).evolve(status="running")
        self.store.create_run(snapshot)
        self.active_run_id = snapshot.run_id
        return snapshot

    def cancel(self, run_id: str) -> RunSnapshot:
        self.calls.append(("cancel", run_id))
        self._raise("cancel")
        snapshot = self.store.read_snapshot(run_id)
        updated = replace(snapshot, status="cancel_requested")
        self.store.write_snapshot_atomic(updated)
        return updated

    def retry(self, run_id: str) -> RunSnapshot:
        self.calls.append(("retry", run_id))
        self._raise("retry")
        source = self.store.read_snapshot(run_id)
        retried = _snapshot(ticker=source.ticker, retry_of=run_id)
        self.store.create_run(retried)
        return retried

    def resume(self, run_id: str) -> RunSnapshot:
        self.calls.append(("resume", run_id))
        self._raise("resume")
        source = self.store.read_snapshot(run_id)
        resumed = source.evolve(
            status="running",
            resumed_from_sequence=source.latest_sequence,
        )
        self.store.write_snapshot_atomic(resumed)
        return resumed


@pytest.fixture
def api(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    manager = RecordingManager(store)
    broker = EventBroker(store)
    app = _create_app(store=store, manager=manager, broker=broker)
    return TestClient(app), store, manager


def _all_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _all_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_strings(child)


def test_config_uses_runtime_catalog_and_exposes_status_not_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    secret = "sk-story-e3-must-never-reach-the-browser"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    store = RunStore(tmp_path / "runs")
    manager = RecordingManager(store)
    client = TestClient(
        _create_app(store=store, manager=manager, broker=EventBroker(store))
    )

    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    providers = {entry["id"]: entry for entry in payload["providers"]}
    assert providers["openai"]["configured"] is True
    assert "gpt-5.4-mini" in str(providers["openai"])
    assert "gpt-5.5" in str(providers["openai"])
    assert {item["id"] for item in payload["analysts"]} == {
        "market",
        "social",
        "news",
        "fundamentals",
    }
    assert payload["depths"] == [1, 3, 5]
    assert "English" in payload["output_languages"]
    assert "Chinese" in payload["output_languages"]
    assert isinstance(payload["checkpoint_available"], bool)
    assert secret not in response.text
    assert not any(value == os.environ["OPENAI_API_KEY"] for value in _all_strings(payload))


def test_application_lifespan_reconciles_orphaned_runs_before_serving(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    manager = RecordingManager(store)
    recover_calls: list[str] = []

    def recover_startup():
        recover_calls.append("recover")
        return ()

    manager.recover_startup = recover_startup  # type: ignore[attr-defined]
    app = _create_app(store=store, manager=manager, broker=EventBroker(store))

    with TestClient(app) as client:
        response = client.get("/api/config")

    assert response.status_code == 200
    assert recover_calls == ["recover"]


def test_azure_is_not_ready_with_only_an_api_key(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    manager = RecordingManager(store)
    incomplete = {"AZURE_OPENAI_API_KEY": "never-return-this-key"}
    client = TestClient(
        _create_app(
            store=store,
            manager=manager,
            broker=EventBroker(store),
            environment=incomplete,
        )
    )
    body = {
        **VALID_RUN_BODY,
        "llm_provider": "azure",
        "quick_think_llm": "fast-deployment",
        "deep_think_llm": "deep-deployment",
    }

    config = client.get("/api/config")
    created = client.post("/api/runs", json=body)

    providers = {item["id"]: item for item in config.json()["providers"]}
    assert providers["azure"]["configured"] is False
    assert created.status_code == 422
    assert created.json()["detail"]["code"] == "missing_configuration"
    assert manager.calls == []
    assert "never-return-this-key" not in config.text + created.text


def test_azure_readiness_requires_endpoint_and_api_version(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    manager = RecordingManager(store)
    environment = {
        "AZURE_OPENAI_API_KEY": "never-return-this-key",
        "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
        "OPENAI_API_VERSION": "2025-03-01-preview",
    }
    client = TestClient(
        _create_app(
            store=store,
            manager=manager,
            broker=EventBroker(store),
            environment=environment,
        )
    )

    response = client.get("/api/config")

    providers = {item["id"]: item for item in response.json()["providers"]}
    assert providers["azure"]["configured"] is True
    assert not any(value in response.text for value in environment.values())


def test_create_validates_and_translates_only_safe_input_before_start(api):
    client, store, manager = api

    response = client.post("/api/runs", json=VALID_RUN_BODY)

    assert response.status_code == 201
    assert len(manager.calls) == 1
    operation, (request, configured_keys) = manager.calls[0]
    assert operation == "start"
    assert request == AnalysisRequest(
        ticker="AAPL",
        analysis_date="2026-07-18",
        asset_type="stock",
        selected_analysts=("market", "fundamentals"),
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        effective_config=request.effective_config,
    )
    assert request.effective_config["llm_provider"] == "openai"
    assert request.effective_config["quick_think_llm"] == "gpt-5.4-mini"
    assert request.effective_config["deep_think_llm"] == "gpt-5.5"
    assert request.effective_config["output_language"] == "Chinese"
    assert request.effective_config["checkpoint_enabled"] is False
    assert all(isinstance(value, bool) for value in configured_keys.values())
    assert "api_key" not in str(request.effective_config).lower()
    created = store.read_snapshot(response.json()["run_id"])
    assert response.json() == jsonable_encoder(created)


def test_create_rejects_missing_provider_key_before_manager(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    manager = RecordingManager(store)
    client = TestClient(
        _create_app(
            store=store,
            manager=manager,
            broker=EventBroker(store),
            environment={},
        )
    )

    response = client.post("/api/runs", json=VALID_RUN_BODY)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "missing_configuration"
    assert manager.calls == []


def test_create_rejects_future_date_and_unavailable_checkpoint_before_manager(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-but-never-returned")
    store = RunStore(tmp_path / "runs")
    manager = RecordingManager(store)
    client = TestClient(
        _create_app(
            store=store,
            manager=manager,
            broker=EventBroker(store),
            checkpoint_available=False,
        )
    )
    future = dict(VALID_RUN_BODY)
    future["analysis_date"] = (date.today() + timedelta(days=1)).isoformat()
    checkpoint = dict(VALID_RUN_BODY)
    checkpoint["checkpoint_enabled"] = True

    future_response = client.post("/api/runs", json=future)
    checkpoint_response = client.post("/api/runs", json=checkpoint)

    assert future_response.status_code == 422
    assert checkpoint_response.status_code == 422
    assert checkpoint_response.json()["detail"]["code"] == "checkpoint_unavailable"
    assert manager.calls == []


def test_create_normalizes_crypto_identity_before_manager(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    manager = RecordingManager(store)
    client = TestClient(
        _create_app(
            store=store,
            manager=manager,
            broker=EventBroker(store),
            environment={},
        )
    )
    body = {
        **VALID_RUN_BODY,
        "ticker": "BTCUSD",
        "asset_type": "crypto",
        "selected_analysts": ["market", "news"],
        "llm_provider": "ollama",
        "quick_think_llm": "local-fast",
        "deep_think_llm": "local-deep",
    }

    response = client.post("/api/runs", json=body)

    assert response.status_code == 201
    request = manager.calls[0][1][0]
    assert request.ticker == "BTC-USD"
    assert request.asset_type == "crypto"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticker", "  "),
        ("ticker", ".."),
        ("ticker", "../../etc/passwd"),
        ("analysis_date", "2026-02-30"),
        ("asset_type", "forex"),
        ("selected_analysts", []),
        ("selected_analysts", ["market", "market"]),
        ("selected_analysts", ["market", "fortune_teller"]),
        ("llm_provider", "not-a-provider"),
        ("quick_think_llm", "claude-sonnet-5"),
        ("deep_think_llm", "not-an-openai-model"),
        ("research_depth", 2),
        ("output_language", "  "),
        ("output_language", "x" * 129),
    ],
)
def test_invalid_create_request_never_reaches_manager(api, field: str, value: Any):
    client, _store, manager = api
    body = dict(VALID_RUN_BODY)
    body[field] = value

    response = client.post("/api/runs", json=body)

    assert response.status_code == 422
    assert manager.calls == []


def test_run_history_and_snapshot_are_newest_first_and_secret_free(api):
    client, store, _manager = api
    secret = "never-return-run-metadata-secret"
    older = _snapshot(
        ticker="MSFT",
        status="completed",
        created_at="2026-07-17T01:00:00.000Z",
        updated_at="2026-07-17T02:00:00.000Z",
        metadata={"api_key": secret},
    )
    newer = _snapshot(
        ticker="AAPL",
        status="failed",
        created_at="2026-07-18T01:00:00.000Z",
        updated_at="2026-07-18T02:00:00.000Z",
    )
    store.create_run(older)
    store.create_run(newer)

    listed = client.get("/api/runs")
    read = client.get(f"/api/runs/{older.run_id}")

    assert listed.status_code == 200
    assert [item["run_id"] for item in listed.json()] == [newer.run_id, older.run_id]
    assert read.status_code == 200
    assert read.json()["metadata"]["api_key"] == "[REDACTED]"
    assert secret not in listed.text + read.text


def test_cancel_retry_and_resume_delegate_to_manager_with_expected_http_semantics(api):
    client, store, manager = api
    active = _snapshot(status="running")
    failed = _snapshot(status="failed")
    interrupted = _snapshot(status="interrupted")
    for snapshot in (active, failed, interrupted):
        store.create_run(snapshot)

    cancelled = client.post(f"/api/runs/{active.run_id}/cancel")
    retried = client.post(f"/api/runs/{failed.run_id}/retry")
    resumed = client.post(f"/api/runs/{interrupted.run_id}/resume")

    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "cancel_requested"
    assert retried.status_code == 201
    assert retried.json()["retry_of"] == failed.run_id
    assert retried.json()["run_id"] != failed.run_id
    assert resumed.status_code == 202
    assert resumed.json()["run_id"] == interrupted.run_id
    assert [call[0] for call in manager.calls] == ["cancel", "retry", "resume"]


@pytest.mark.parametrize(
    ("operation", "error", "code"),
    [
        ("start", ActiveRunConflict("run_20260718T000000000000Z_aaaaaaaa"), "active_run_conflict"),
        ("cancel", RunNotActive("not active"), "run_not_active"),
        ("retry", RunNotRetryable("not retryable"), "run_not_retryable"),
        ("resume", RunNotResumable("no checkpoint"), "run_not_resumable"),
    ],
)
def test_lifecycle_conflicts_have_stable_safe_409_errors(
    api,
    operation: str,
    error: BaseException,
    code: str,
):
    client, store, manager = api
    source = _snapshot(status="interrupted")
    store.create_run(source)
    manager.errors[operation] = error
    if operation == "start":
        response = client.post("/api/runs", json=VALID_RUN_BODY)
    else:
        response = client.post(f"/api/runs/{source.run_id}/{operation}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == code


def test_resume_mismatch_returns_only_allowlisted_safe_field_names(api):
    client, store, manager = api
    secret = "sk-do-not-trust-exception-message"
    interrupted = _snapshot(status="interrupted")
    store.create_run(interrupted)
    manager.errors["resume"] = ResumeRunConflict(
        f"fingerprint mismatch included {secret}",
        fields=(
            "OPENAI_API_KEY",
            "effective_config.OPENAI_API_KEY.value",
            "field=secret-value",
            "unknown_field",
            "llm_provider",
            "quick_think_llm",
        ),
    )

    response = client.post(f"/api/runs/{interrupted.run_id}/resume")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "resume_conflict",
        "message": "The stored run is incompatible with the current runtime.",
        "fields": ["llm_provider", "quick_think_llm"],
    }
    assert secret not in response.text
    assert "OPENAI_API_KEY" not in response.text


def test_missing_or_invalid_run_is_json_404_and_never_spa(api):
    client, _store, _manager = api

    missing = client.get("/api/runs/run_20260718T000000000000Z_aaaaaaaa")
    invalid = client.get("/api/runs/not-a-run")

    for response in (missing, invalid):
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")


def _artifact_event(run_id: str, ref) -> RunEventDraft:
    return RunEventDraft(
        run_id,
        "artifact.written",
        {
            "artifact_id": ref.artifact_id,
            "kind": ref.kind,
            "media_type": ref.media_type,
            "content_sha256": ref.content_sha256,
            "byte_size": ref.byte_size,
            "locator": ref.locator,
        },
    )


@pytest.mark.parametrize(
    ("kind", "value", "media_type", "expected"),
    [
        (
            "data",
            {"rows": [{"field": "revenue", "value": 42}]},
            "application/json",
            "json",
        ),
        ("report-revision", "# Partial report\n", "text/markdown", "markdown"),
        ("tool-result", "plain result", "text/plain", "plain"),
    ],
)
def test_artifact_list_is_metadata_only_and_read_preserves_content_type(
    api,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    value: Any,
    media_type: str,
    expected: str,
):
    client, store, _manager = api
    run = _snapshot(status="failed")
    store.create_run(run)
    if kind == "report-revision":
        ref = ReportArtifactWriter(store).write_revision(
            run.run_id,
            "market",
            str(value),
        ).artifact
    else:
        ref = store.store_artifact(
            run.run_id,
            kind=kind,
            value=value,
            media_type=media_type,
        )
    store.append_event(_artifact_event(run.run_id, ref))
    original_read = store.read_artifact
    reads: list[tuple[str, str]] = []

    def tracked_read(run_id: str, artifact_id: str) -> bytes:
        reads.append((run_id, artifact_id))
        return original_read(run_id, artifact_id)

    monkeypatch.setattr(store, "read_artifact", tracked_read)

    listed = client.get(f"/api/runs/{run.run_id}/artifacts")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    metadata = listed.json()[0]
    assert metadata["artifact_id"] == ref.artifact_id
    assert metadata["kind"] == kind
    assert metadata["media_type"] == media_type
    assert metadata["content_sha256"] == ref.content_sha256
    assert metadata["byte_size"] == ref.byte_size
    assert reads == [], "listing metadata must not eagerly read artifact bodies"

    read = client.get(f"/api/runs/{run.run_id}/artifacts/{ref.artifact_id}")
    assert read.status_code == 200
    assert read.headers["content-type"].startswith(media_type)
    assert reads == [(run.run_id, ref.artifact_id)]
    if expected == "json":
        assert read.json() == value
    elif expected == "markdown":
        assert read.text == value
    else:
        assert read.text == value


def test_artifact_reads_are_run_scoped_and_reject_traversal(api):
    client, store, _manager = api
    owner = _snapshot(status="failed")
    other = _snapshot(status="failed")
    store.create_run(owner)
    store.create_run(other)
    ref = store.store_artifact(
        owner.run_id,
        kind="data",
        value={"private": "owner only"},
    )
    store.append_event(_artifact_event(owner.run_id, ref))

    cross_run = client.get(f"/api/runs/{other.run_id}/artifacts/{ref.artifact_id}")
    traversal = client.get(
        f"/api/runs/{owner.run_id}/artifacts/%2E%2E%2F%2E%2E%2Frun.json"
    )

    assert cross_run.status_code == 404
    assert traversal.status_code in {404, 422}
    assert "owner only" not in cross_run.text + traversal.text


def test_static_assets_spa_fallback_and_csp_do_not_capture_api_paths(
    tmp_path: Path,
):
    static_dir = tmp_path / "frontend"
    assets = static_dir / "assets"
    assets.mkdir(parents=True)
    (static_dir / "index.html").write_text(
        "<!doctype html><title>workbench-shell-marker</title>",
        encoding="utf-8",
    )
    (assets / "app.js").write_text("window.workbench = true;", encoding="utf-8")
    store = RunStore(tmp_path / "runs")
    manager = RecordingManager(store)
    client = TestClient(
        _create_app(
            store=store,
            manager=manager,
            broker=EventBroker(store),
            static_dir=static_dir,
        )
    )

    root = client.get("/")
    history_route = client.get("/history/some-safe-client-route")
    asset = client.get("/assets/app.js")
    missing_api = client.get("/api/definitely-not-a-route")

    for response in (root, history_route):
        assert response.status_code == 200
        assert "workbench-shell-marker" in response.text
        csp = response.headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "connect-src 'self'" in csp
        assert "object-src 'none'" in csp
    assert asset.status_code == 200
    assert asset.headers["content-type"].startswith(
        ("text/javascript", "application/javascript")
    )
    assert "window.workbench" in asset.text
    assert missing_api.status_code == 404
    assert missing_api.headers["content-type"].startswith("application/json")
    assert "workbench-shell-marker" not in missing_api.text
