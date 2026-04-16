import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def _load_main_module(monkeypatch, *, env_file=""):
    backend_dir = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("TRADINGAGENTS_ENV_FILE", env_file)
    monkeypatch.syspath_prepend(str(backend_dir))
    sys.modules.pop("main", None)
    return importlib.import_module("main")


def test_config_check_smoke(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    main = _load_main_module(monkeypatch)

    with TestClient(main.app) as client:
        response = client.get("/api/config/check")

    assert response.status_code == 200
    assert response.json() == {"configured": False}


def test_repo_env_overrides_stale_shell_provider_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TRADINGAGENTS_LLM_PROVIDER=anthropic",
                "TRADINGAGENTS_BACKEND_URL=https://api.minimaxi.com/anthropic",
                "TRADINGAGENTS_MODEL=MiniMax-M2.7-highspeed",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TRADINGAGENTS_BACKEND_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("TRADINGAGENTS_MODEL", "gpt-5.4")

    main = _load_main_module(monkeypatch, env_file=str(env_file))

    settings = main._resolve_analysis_runtime_settings()

    assert settings["llm_provider"] == "anthropic"
    assert settings["backend_url"] == "https://api.minimaxi.com/anthropic"
    assert settings["deep_think_llm"] == "MiniMax-M2.7-highspeed"
    assert settings["quick_think_llm"] == "MiniMax-M2.7-highspeed"


def test_saved_api_key_is_provider_scoped(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    main = _load_main_module(monkeypatch)
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(main, "CONFIG_PATH", config_path)

    main._persist_analysis_api_key("anth-key", provider="anthropic")

    saved = json.loads(config_path.read_text())
    assert saved["api_keys"]["anthropic"] == "anth-key"
    assert main._get_analysis_provider_api_key("anthropic", saved) == "anth-key"
    assert main._get_analysis_provider_api_key("openai", saved) is None


def test_analysis_task_routes_smoke(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    main = _load_main_module(monkeypatch)

    seeded_task = {
        "contract_version": "v1alpha1",
        "task_id": "task-smoke",
        "request_id": "req-task-smoke",
        "executor_type": "legacy_subprocess",
        "result_ref": None,
        "ticker": "AAPL",
        "date": "2026-04-11",
        "status": "running",
        "progress": 10,
        "current_stage": "analysts",
        "created_at": "2026-04-11T10:00:00",
        "elapsed_seconds": 1,
        "stages": [],
        "result": None,
        "error": None,
        "degradation_summary": None,
        "data_quality_summary": None,
        "compat": {},
    }

    with TestClient(main.app) as client:
        main.app.state.task_results["task-smoke"] = seeded_task

        health_response = client.get("/health")
        tasks_response = client.get("/api/analysis/tasks")
        status_response = client.get("/api/analysis/status/task-smoke")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert tasks_response.status_code == 200
    assert tasks_response.json()["total"] >= 1
    assert any(task["task_id"] == "task-smoke" for task in tasks_response.json()["tasks"])
    assert status_response.status_code == 200
    assert status_response.json()["task_id"] == "task-smoke"
    assert status_response.json()["contract_version"] == "v1alpha1"
    assert status_response.json()["request_id"] == "req-task-smoke"
    assert status_response.json()["result"] is None


def test_analysis_status_route_uses_task_query_service(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    main = _load_main_module(monkeypatch)
    expected = {
        "contract_version": "v1alpha1",
        "task_id": "task-query",
        "status": "running",
        "via": "task-query-service",
    }

    def _fake_public_task_payload(task_id, *, state_override=None):
        assert task_id == "task-query"
        assert state_override is None
        return expected

    with TestClient(main.app) as client:
        main.app.state.task_results["task-query"] = {
            "contract_version": "v1alpha1",
            "task_id": "task-query",
            "request_id": "req-task-query",
            "executor_type": "legacy_subprocess",
            "result_ref": None,
            "ticker": "AAPL",
            "date": "2026-04-11",
            "status": "running",
            "progress": 10,
            "current_stage": "analysts",
            "created_at": "2026-04-11T10:00:00",
            "elapsed_seconds": 1,
            "stages": [],
            "result": None,
            "error": None,
            "degradation_summary": None,
            "data_quality_summary": None,
            "compat": {},
        }
        monkeypatch.setattr(main.app.state.task_query_service, "public_task_payload", _fake_public_task_payload)
        response = client.get("/api/analysis/status/task-query")

    assert response.status_code == 200
    assert response.json() == expected


def test_analysis_tasks_route_uses_task_query_service(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    main = _load_main_module(monkeypatch)
    expected = {
        "contract_version": "v1alpha1",
        "tasks": [{"task_id": "task-query"}],
        "total": 1,
    }

    def _fake_list_task_summaries():
        return expected

    with TestClient(main.app) as client:
        monkeypatch.setattr(main.app.state.task_query_service, "list_task_summaries", _fake_list_task_summaries)
        response = client.get("/api/analysis/tasks")

    assert response.status_code == 200
    assert response.json() == expected


def test_analysis_start_route_uses_analysis_service(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    main = _load_main_module(monkeypatch)
    created: dict[str, object] = {}

    class DummyTask:
        def cancel(self):
            return None

    def fake_create_task(coro):
        created["scheduled_coro"] = coro.cr_code.co_name
        coro.close()
        task = DummyTask()
        created["task"] = task
        return task

    monkeypatch.setattr(main.asyncio, "create_task", fake_create_task)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/analysis/start",
            json={"ticker": "AAPL", "date": "2026-04-11"},
            headers={"api-key": "test-key"},
        )

    payload = response.json()
    task_id = payload["task_id"]

    assert response.status_code == 200
    assert payload["ticker"] == "AAPL"
    assert payload["date"] == "2026-04-11"
    assert payload["status"] == "running"
    assert created["scheduled_coro"] == "_run_analysis"
    assert main.app.state.analysis_tasks[task_id] is created["task"]
    assert main.app.state.task_results[task_id]["current_stage"] == "analysts"
    assert main.app.state.task_results[task_id]["status"] == "running"
    assert main.app.state.task_results[task_id]["request_id"]
    assert main.app.state.task_results[task_id]["executor_type"] == "legacy_subprocess"
    assert main.app.state.task_results[task_id]["result_ref"] is None
    assert main.app.state.task_results[task_id]["compat"] == {}


def test_portfolio_analyze_route_uses_analysis_service_smoke(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.setenv("TRADINGAGENTS_USE_APPLICATION_SERVICES", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "service-key")

    main = _load_main_module(monkeypatch)
    captured: dict[str, object] = {}

    async def fake_start_portfolio_analysis(*, task_id, date, request_context, broadcast_progress):
        captured["task_id"] = task_id
        captured["date"] = date
        captured["request_context"] = request_context
        captured["broadcast_progress"] = broadcast_progress
        return {"task_id": task_id, "status": "running", "total": 3}

    with TestClient(main.app) as client:
        monkeypatch.setattr(main.app.state.analysis_service, "start_portfolio_analysis", fake_start_portfolio_analysis)
        response = client.post("/api/portfolio/analyze", headers={"api-key": "service-key"})

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert str(captured["task_id"]).startswith("port_")
    assert isinstance(captured["date"], str)
    assert captured["request_context"].auth_key == "service-key"
    assert callable(captured["broadcast_progress"])


def test_analysis_websocket_progress_is_contract_first(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    main = _load_main_module(monkeypatch)

    with TestClient(main.app) as client:
        main.app.state.task_results["task-ws"] = {
            "contract_version": "v1alpha1",
            "task_id": "task-ws",
            "request_id": "req-task-ws",
            "executor_type": "legacy_subprocess",
            "result_ref": None,
            "ticker": "AAPL",
            "date": "2026-04-11",
            "status": "running",
            "progress": 50,
            "current_stage": "research",
            "created_at": "2026-04-11T10:00:00",
            "elapsed_seconds": 3,
            "stages": [],
            "result": None,
            "error": None,
            "degradation_summary": None,
            "data_quality_summary": None,
            "compat": {"decision": "HOLD"},
        }
        with client.websocket_connect("/ws/analysis/task-ws?api_key=test-key") as websocket:
            message = websocket.receive_json()

    assert message["type"] == "progress"
    assert message["contract_version"] == "v1alpha1"
    assert message["task_id"] == "task-ws"
    assert message["request_id"] == "req-task-ws"
    assert message["compat"]["decision"] == "HOLD"
    assert "decision" not in message


def test_analysis_websocket_maps_internal_runtime_status_to_running(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    main = _load_main_module(monkeypatch)

    with TestClient(main.app) as client:
        main.app.state.task_results["task-ws-runtime"] = {
            "contract_version": "v1alpha1",
            "task_id": "task-ws-runtime",
            "request_id": "req-task-ws-runtime",
            "executor_type": "legacy_subprocess",
            "result_ref": None,
            "ticker": "AAPL",
            "date": "2026-04-11",
            "status": "auto_recovering",
            "progress": 50,
            "current_stage": "research",
            "created_at": "2026-04-11T10:00:00",
            "elapsed_seconds": 3,
            "stages": [],
            "result": None,
            "error": None,
            "degradation_summary": None,
            "data_quality_summary": None,
            "evidence_summary": {"attempts": []},
            "tentative_classification": None,
            "budget_state": {},
            "compat": {},
        }
        with client.websocket_connect("/ws/analysis/task-ws-runtime?api_key=test-key") as websocket:
            message = websocket.receive_json()

    assert message["status"] == "running"


def test_analysis_cancel_route_preserves_response_shape_and_broadcasts_cancelled_state(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    main = _load_main_module(monkeypatch)

    class _DummyTask:
        def cancel(self):
            return None

    class _DummyProcess:
        returncode = None

        def kill(self):
            return None

    captured: dict[str, dict] = {}

    def _save_sync(task_id, data):
        captured["saved_state"] = json.loads(json.dumps(data))

    def _delete_sync(task_id):
        captured["deleted_task_id"] = task_id

    async def _fake_broadcast(task_id, progress):
        captured["broadcast_payload"] = main.app.state.task_query_service.public_task_payload(
            task_id,
            state_override=progress,
        )

    with TestClient(main.app) as client:
        main.app.state.task_results["task-cancel"] = {
            "contract_version": "v1alpha1",
            "task_id": "task-cancel",
            "request_id": "req-task-cancel",
            "executor_type": "legacy_subprocess",
            "result_ref": None,
            "ticker": "AAPL",
            "date": "2026-04-11",
            "status": "running",
            "progress": 25,
            "current_stage": "research",
            "created_at": "2026-04-11T10:00:00",
            "elapsed_seconds": 4,
            "stages": [],
            "result": None,
            "error": None,
            "degradation_summary": None,
            "data_quality_summary": None,
            "compat": {},
        }
        main.app.state.analysis_tasks["task-cancel"] = _DummyTask()
        main.app.state.processes["task-cancel"] = _DummyProcess()
        monkeypatch.setattr(main.app.state.result_store, "save_task_status", _save_sync)
        monkeypatch.setattr(main.app.state.result_store, "delete_task_status", _delete_sync)
        monkeypatch.setattr(main, "broadcast_progress", _fake_broadcast)
        response = client.delete("/api/analysis/cancel/task-cancel")

    assert response.status_code == 200
    assert response.json() == {
        "contract_version": "v1alpha1",
        "task_id": "task-cancel",
        "status": "cancelled",
    }
    assert "error" not in response.json()
    assert captured["saved_state"]["status"] == "cancelled"
    assert captured["broadcast_payload"]["status"] == "cancelled"
    assert captured["broadcast_payload"]["error"] == {
        "code": "cancelled",
        "message": "用户取消",
        "retryable": False,
    }
    assert captured["deleted_task_id"] == "task-cancel"


def test_orchestrator_websocket_smoke_is_contract_first(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    main = _load_main_module(monkeypatch)

    import orchestrator.config as config_module
    import orchestrator.live_mode as live_mode_module
    import orchestrator.orchestrator as orchestrator_module

    class DummyConfig:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class DummyOrchestrator:
        def __init__(self, config):
            self.config = config

    class DummyLiveMode:
        def __init__(self, orchestrator):
            self.orchestrator = orchestrator

        async def run_once(self, tickers, date=None):
            assert tickers == ["AAPL"]
            assert date == "2026-04-11"
            return [
                {
                    "contract_version": "v1alpha1",
                    "ticker": "AAPL",
                    "date": "2026-04-11",
                    "status": "degraded_success",
                    "result": {
                        "direction": 1,
                        "confidence": 0.55,
                        "quant_direction": None,
                        "llm_direction": 1,
                        "timestamp": "2026-04-11T12:00:00+00:00",
                    },
                    "error": None,
                    "degradation": {
                        "degraded": True,
                        "reason_codes": ["quant_signal_failed"],
                        "source_diagnostics": {"quant": {"reason_code": "quant_signal_failed"}},
                    },
                    "data_quality": {"state": "partial_data", "source": "quant"},
                }
            ]

    monkeypatch.setattr(config_module, "OrchestratorConfig", DummyConfig)
    monkeypatch.setattr(orchestrator_module, "TradingOrchestrator", DummyOrchestrator)
    monkeypatch.setattr(live_mode_module, "LiveMode", DummyLiveMode)

    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/orchestrator?api_key=test-key") as websocket:
            websocket.send_json({"tickers": ["AAPL"], "date": "2026-04-11"})
            message = websocket.receive_json()

    assert message["contract_version"] == "v1alpha1"
    assert message["signals"][0]["contract_version"] == "v1alpha1"
    assert message["signals"][0]["status"] == "degraded_success"
    assert message["signals"][0]["degradation"]["reason_codes"] == ["quant_signal_failed"]
    assert message["signals"][0]["data_quality"]["state"] == "partial_data"


def test_orchestrator_websocket_rejects_unauthorized(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", "dashboard-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    main = _load_main_module(monkeypatch)

    with TestClient(main.app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/orchestrator"):
                pass

    assert exc_info.value.code == 4401
