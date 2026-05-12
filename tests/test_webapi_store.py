from tradingagents.webapi.schemas import AnalysisRequest, SettingsPayload
from tradingagents.webapi.store import SQLiteWebStore


def test_store_persists_runs_events_and_requests(tmp_path):
    db_path = tmp_path / "web.sqlite3"
    store = SQLiteWebStore(db_path)
    request = AnalysisRequest(ticker=" nvda ", analysts=["market"], use_mock_stream=False)
    run = {
        "id": "run_1",
        "ticker": request.ticker,
        "company_name": None,
        "analysis_date": request.analysis_date,
        "status": "queued",
        "created_at": "2026-05-12T00:00:00+00:00",
        "updated_at": "2026-05-12T00:00:00+00:00",
        "decision": None,
        "title": "NVDA research",
    }
    event = {
        "id": "evt_1",
        "runId": "run_1",
        "type": "run_status",
        "agent": None,
        "status": "running",
        "section": None,
        "content": "started",
        "payload": {},
        "createdAt": "2026-05-12T00:00:01+00:00",
    }

    store.save_run(run, request)
    store.append_event("run_1", event)
    store.update_run("run_1", status="running", updated_at=event["createdAt"], decision="HOLD")

    reloaded = SQLiteWebStore(db_path)

    assert reloaded.get_run("run_1")["status"] == "running"
    assert reloaded.get_run("run_1")["decision"] == "HOLD"
    assert reloaded.get_request("run_1").ticker == "NVDA"
    assert reloaded.get_request("run_1").use_mock_stream is False
    assert reloaded.get_events("run_1")[0]["content"] == "started"
    assert reloaded.list_runs()[0]["id"] == "run_1"


def test_store_persists_settings_and_api_keys(tmp_path, monkeypatch):
    db_path = tmp_path / "web.sqlite3"
    store = SQLiteWebStore(db_path)
    settings = SettingsPayload(llm_provider="deepseek", deep_think_llm="deepseek-reasoner")

    store.save_settings(settings)
    store.save_api_key("deepseek", "sk-test-secret")

    reloaded = SQLiteWebStore(db_path)
    reloaded.apply_api_keys_to_env(monkeypatch.setenv)

    assert reloaded.get_settings().llm_provider == "deepseek"
    assert reloaded.get_settings().deep_think_llm == "deepseek-reasoner"
    assert reloaded.get_api_key("deepseek") == "sk-test-secret"
    assert reloaded.get_masked_api_keys()["deepseek"] == "sk-t*******ret"
