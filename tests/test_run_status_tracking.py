import asyncio
import importlib
import sys
import types

import pytest


class _FakeHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _FakeFastAPI:
    def __init__(self, *args, **kwargs):
        self.routes = []

    def add_middleware(self, *args, **kwargs):
        return None

    def mount(self, *args, **kwargs):
        return None

    def get(self, *args, **kwargs):
        def decorator(func):
            self.routes.append(("GET", args, func))
            return func
        return decorator

    def post(self, *args, **kwargs):
        def decorator(func):
            self.routes.append(("POST", args, func))
            return func
        return decorator


@pytest.fixture()
def backend_module(monkeypatch):
    fastapi_mod = types.ModuleType("fastapi")
    fastapi_mod.FastAPI = _FakeFastAPI
    fastapi_mod.HTTPException = _FakeHTTPException
    monkeypatch.setitem(sys.modules, "fastapi", fastapi_mod)

    cors_mod = types.ModuleType("fastapi.middleware.cors")
    cors_mod.CORSMiddleware = object
    monkeypatch.setitem(sys.modules, "fastapi.middleware.cors", cors_mod)

    static_mod = types.ModuleType("fastapi.staticfiles")
    static_mod.StaticFiles = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "fastapi.staticfiles", static_mod)

    responses_mod = types.ModuleType("fastapi.responses")
    responses_mod.FileResponse = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "fastapi.responses", responses_mod)

    module = importlib.import_module("ui.backend.main")
    module = importlib.reload(module)
    with module.run_status_lock:
        module.run_statuses.clear()
        module.latest_run_id = None
    return module


@pytest.mark.unit
def test_webhook_updates_are_isolated_by_run_id(backend_module):
    asyncio.run(
        backend_module.handle_progress_webhook(
            {
                "run_id": "run-a",
                "ticker": "AAPL",
                "date": "2026-05-15",
                "node": "Market Analyst",
                "status": "in_progress",
                "timestamp": "2026-05-15T12:00:00Z",
                "start_time": "2026-05-15T12:00:00Z",
                "updates": {"market_report": "AAPL market"},
            }
        )
    )
    asyncio.run(
        backend_module.handle_progress_webhook(
            {
                "run_id": "run-b",
                "ticker": "MSFT",
                "date": "2026-05-15",
                "node": "News Analyst",
                "status": "in_progress",
                "timestamp": "2026-05-15T12:00:01Z",
                "start_time": "2026-05-15T12:00:01Z",
                "updates": {"news_report": "MSFT news"},
            }
        )
    )

    run_a = asyncio.run(backend_module.get_run_status("run-a"))
    run_b = asyncio.run(backend_module.get_run_status("run-b"))

    assert run_a["ticker"] == "AAPL"
    assert run_b["ticker"] == "MSFT"
    assert run_a["updates"]["market_report"] == "AAPL market"
    assert run_b["updates"]["news_report"] == "MSFT news"
    assert "MSFT" not in run_a["tickers"]
    assert "AAPL" not in run_b["tickers"]


@pytest.mark.unit
def test_latest_status_endpoint_returns_most_recent_run(backend_module):
    asyncio.run(
        backend_module.handle_progress_webhook(
            {
                "run_id": "run-1",
                "ticker": "AAPL",
                "date": "2026-05-15",
                "node": "Market Analyst",
                "status": "in_progress",
                "timestamp": "2026-05-15T12:00:00Z",
                "start_time": "2026-05-15T12:00:00Z",
            }
        )
    )
    asyncio.run(
        backend_module.handle_progress_webhook(
            {
                "run_id": "run-2",
                "ticker": "NVDA",
                "date": "2026-05-15",
                "node": "News Analyst",
                "status": "in_progress",
                "timestamp": "2026-05-15T12:00:05Z",
                "start_time": "2026-05-15T12:00:05Z",
            }
        )
    )

    latest = asyncio.run(backend_module.get_current_status())

    assert latest["run_id"] == "run-2"
    assert latest["ticker"] == "NVDA"
