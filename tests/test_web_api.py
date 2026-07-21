"""HTTP API contract: health, providers, config, run lifecycle over HTTP,
SSE replay + terminal semantics, history and report endpoints."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from tradingagents.web.app import create_app
from tradingagents.web.history import write_manifest

pytestmark = pytest.mark.unit


async def scripted_engine(params, emit):
    emit("agent_status", {"agent": "Market Analyst", "team": "Analyst Team", "status": "working"})
    emit("report_section", {"section": "market_report", "markdown": "# hi"})
    emit("stats", {"elapsed": 1.0, "llm_calls": 2, "tool_calls": 3})
    return {"decision": "BUY", "ticker": params["ticker"], "date": params["date"]}


def make_client(tmp_path, engine=scripted_engine, monkeypatch=None):
    app = create_app(engine=engine, results_dir=str(tmp_path))
    return TestClient(app, base_url="http://localhost")


def run_body(**overrides):
    body = {
        "ticker": "AAPL",
        "date": "2026-07-01",
        "asset_type": "stock",
        "analysts": ["market"],
        "research_depth": 1,
        "provider": "openai",
        "deep_think_llm": "gpt-5.5",
        "quick_think_llm": "gpt-5.4-mini",
    }
    body.update(overrides)
    return body


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tradingagents.web.settings._DEFAULT_PATH", tmp_path / "web_settings.json"
    )


def _start_and_finish_run(client, **overrides):
    response = client.post("/api/runs", json=run_body(**overrides))
    assert response.status_code == 201, response.text
    run_id = response.json()["run_id"]
    # The scripted engine terminates immediately; poll until terminal.
    for _ in range(100):
        state = client.get(f"/api/runs/{run_id}").json()
        if state["state"] != "running":
            return run_id, state
    raise AssertionError("run never finished")


def test_health(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_providers_catalog_shape(tmp_path):
    with make_client(tmp_path) as client:
        providers = client.get("/api/providers").json()["providers"]
        by_key = {p["key"]: p for p in providers}
        assert by_key["openai"]["key_status"] == "present"  # conftest placeholder
        assert by_key["openai"]["key_env_var"] == "OPENAI_API_KEY"
        assert by_key["ollama"]["key_status"] == "not-required"
        assert by_key["openai_compatible"]["needs_backend_url"] is True
        assert {"label", "value"} == set(by_key["openai"]["models"]["deep"][0])


def test_run_lifecycle_over_http(tmp_path):
    with make_client(tmp_path) as client:
        run_id, state = _start_and_finish_run(client)
        assert state["state"] == "done"
        assert state["decision"] == "BUY"
        assert state["ticker"] == "AAPL"


def test_unknown_run_404(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/api/runs/nope").status_code == 404
        response = client.post(
            "/api/runs/nope/cancel", headers={"content-type": "application/json"}
        )
        assert response.status_code == 404


def test_second_run_conflicts_409_with_active_id(tmp_path):
    async def hanging_engine(params, emit):
        await asyncio.sleep(3600)

    with make_client(tmp_path, engine=hanging_engine) as client:
        first = client.post("/api/runs", json=run_body()).json()
        conflict = client.post("/api/runs", json=run_body(ticker="MSFT"))
        assert conflict.status_code == 409
        assert conflict.json()["active_run_id"] == first["run_id"]

        cancel = client.post(
            f"/api/runs/{first['run_id']}/cancel",
            headers={"content-type": "application/json"},
        )
        assert cancel.status_code == 200
        for _ in range(200):
            if client.get(f"/api/runs/{first['run_id']}").json()["state"] == "cancelled":
                break
        # Idempotent second cancel.
        again = client.post(
            f"/api/runs/{first['run_id']}/cancel",
            headers={"content-type": "application/json"},
        )
        assert again.status_code == 200


def test_missing_key_rejected_naming_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "")
    with make_client(tmp_path) as client:
        response = client.post("/api/runs", json=run_body(provider="xai"))
        assert response.status_code == 422
        assert "XAI_API_KEY" in response.json()["detail"]


def test_validation_rejects_bad_inputs(tmp_path):
    with make_client(tmp_path) as client:
        assert client.post("/api/runs", json=run_body(ticker="../evil")).status_code == 422
        assert client.post("/api/runs", json=run_body(date="07/01/2026")).status_code == 422
        assert client.post("/api/runs", json=run_body(analysts=[])).status_code == 422
        assert client.post("/api/runs", json=run_body(analysts=["quant"])).status_code == 422
        assert client.post("/api/runs", json=run_body(provider="skynet")).status_code == 422


def test_state_changing_endpoints_require_json(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/runs",
            content="ticker=AAPL",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 415


def test_sse_stream_replays_and_terminates(tmp_path):
    with make_client(tmp_path) as client:
        run_id, _ = _start_and_finish_run(client)
        # Fresh connect replays the whole log and closes after the terminal.
        with client.stream("GET", f"/api/runs/{run_id}/events") as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())
        assert "event: run_status" in body
        assert "event: report_section" in body
        assert "event: done" in body

        # data frames must be JSON *objects*, not double-encoded strings.
        first_data = next(
            line for line in body.splitlines() if line.startswith("data:")
        )
        payload = json.loads(first_data.split(":", 1)[1].strip())
        assert isinstance(payload, dict)
        assert payload["ticker"] == "AAPL"

        ids = [
            int(line.split(":", 1)[1].strip())
            for line in body.splitlines()
            if line.startswith("id:")
        ]
        assert ids == sorted(ids)
        assert len(set(ids)) == len(ids)


def test_sse_last_event_id_resumes(tmp_path):
    with make_client(tmp_path) as client:
        run_id, _ = _start_and_finish_run(client)
        with client.stream(
            "GET", f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "3"}
        ) as response:
            body = "".join(response.iter_text())
        ids = [
            int(line.split(":", 1)[1].strip())
            for line in body.splitlines()
            if line.startswith("id:")
        ]
        assert ids and min(ids) == 4
        assert "event: done" in body


def test_history_lists_manifest_and_cli_runs(tmp_path):
    run_dir = tmp_path / "MSFT" / "2026-06-01"
    (run_dir / "reports").mkdir(parents=True)
    write_manifest(run_dir, {"run_id": "x", "ticker": "MSFT", "date": "2026-06-01",
                             "status": "done", "decision": "HOLD"})
    cli_dir = tmp_path / "TSLA" / "2026-05-01" / "reports"
    cli_dir.mkdir(parents=True)

    with make_client(tmp_path) as client:
        payload = client.get("/api/runs").json()
        sources = {(e["ticker"], e["source"]) for e in payload["runs"]}
        assert ("MSFT", "web") in sources
        assert ("TSLA", "cli") in sources
        assert payload["active_run"] is None


def test_report_endpoint_serves_sections(tmp_path):
    reports = tmp_path / "AAPL" / "2026-07-01" / "reports"
    reports.mkdir(parents=True)
    (reports / "market_report.md").write_text("# m", encoding="utf-8")

    with make_client(tmp_path) as client:
        report = client.get("/api/runs/AAPL/2026-07-01/report").json()
        assert report["sections"]["market_report"] == "# m"
        assert client.get("/api/runs/AAPL/2026-07-02/report").status_code == 404
        assert client.get("/api/runs/%2e%2e/2026-07-01/report").status_code in (404, 422)


def test_config_returns_whitelist_and_last_used(tmp_path):
    with make_client(tmp_path) as client:
        _start_and_finish_run(client)
        payload = client.get("/api/config").json()
        assert "results_dir" in payload["config"]
        assert payload["last_used"]["ticker"] == "AAPL"
        assert "backend_url" not in payload["last_used"]


def test_index_serves_html(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert json.loads(client.get("/api/health").text)["status"] == "ok"
