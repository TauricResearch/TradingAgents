"""Tests for the chat router tool discovery and proxy endpoints."""

from fastapi.testclient import TestClient

from web.server.app import create_app


def _make_client(data_root):
    from web.server import runner
    from unittest.mock import AsyncMock, MagicMock

    async def fake_enqueue(*a, **kw):
        return "fake-run-id"

    import pytest  # noqa: F401 – just for the fixture; we call directly
    from web.server import storage
    from web.server.tests.conftest import data_root as _  # noqa: F401

    app = create_app()
    return TestClient(app)


def _app_with_routes():
    """Create a minimal app to test extract_tool_definitions."""
    from fastapi import FastAPI

    test_app = FastAPI()

    @test_app.get("/api/health")
    def health():
        """Health check."""
        return {"status": "ok"}

    @test_app.get("/api/tickers/{ticker}/runs")
    def ticker_runs(ticker: str):
        """List runs for a ticker."""
        return []

    @test_app.post("/api/watchlist")
    def add_watchlist():
        return {}

    @test_app.get("/ws/something")
    def ws_skip():
        return {}

    @test_app.get("/api/chat/tools")
    def chat_skip():
        return {}

    return test_app


def test_extract_tool_definitions_discovers_routes():
    from web.server.chat_router import extract_tool_definitions

    app = _app_with_routes()
    tools = extract_tool_definitions(app)
    names = {t["name"] for t in tools}

    assert "get_health" in names
    assert "get_tickers_{ticker}_runs" in names or "get_tickers_{ticker}_runs" in names
    assert "post_watchlist" in names
    # Chat and WS routes should be excluded
    assert not any(t["path"].startswith("/api/chat") for t in tools)
    assert not any(t["path"].startswith("/ws") for t in tools)


def test_extract_tool_definitions_includes_method_and_path():
    from web.server.chat_router import extract_tool_definitions

    app = _app_with_routes()
    tools = extract_tool_definitions(app)

    health_tool = [t for t in tools if t["name"] == "get_health"][0]
    assert health_tool["method"] == "GET"
    assert health_tool["path"] == "/api/health"
    assert health_tool["description"] == "Health check."


def test_extract_tool_definitions_extracts_path_params():
    from web.server.chat_router import extract_tool_definitions

    app = _app_with_routes()
    tools = extract_tool_definitions(app)

    runs_tool = [t for t in tools if "ticker" in t["name"]][0]
    assert "ticker" in runs_tool["parameters"]
    assert runs_tool["parameters"]["ticker"]["type"] == "string"


def test_extract_tool_definitions_fallback_description():
    from web.server.chat_router import extract_tool_definitions

    from fastapi import FastAPI

    app = FastAPI()

    @app.post("/api/no-docs")
    def no_docs():
        return {}

    tools = extract_tool_definitions(app)
    no_docs_tools = [t for t in tools if t["path"] == "/api/no-docs"]
    assert len(no_docs_tools) == 1
    assert no_docs_tools[0]["description"] == "Execute POST on /api/no-docs"


def test_extract_tool_definitions_root_fallback():
    """Route at '/' gets tool_name='root'."""
    from web.server.chat_router import extract_tool_definitions

    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/api/")
    def root():
        return {}

    tools = extract_tool_definitions(app)
    root_tools = [t for t in tools if t["path"] == "/api/"]
    assert len(root_tools) == 1
    assert root_tools[0]["name"] == "get_root"


class TestGetToolsEndpoint:
    """GET /api/chat/tools returns auto-generated tool definitions."""

    def test_returns_200_with_tools_list(self, data_root):
        from web.server import runner
        from unittest.mock import AsyncMock

        import pytest  # noqa: F401
        from web.server.tests.conftest import data_root as _  # noqa: F401

        app = create_app()
        with TestClient(app) as client:
            r = client.get("/api/chat/tools")
            assert r.status_code == 200
            body = r.json()
            assert "tools" in body
            assert isinstance(body["tools"], list)
            assert len(body["tools"]) > 0

    def test_tool_shape(self, data_root):
        from web.server import runner
        from unittest.mock import AsyncMock

        import pytest  # noqa: F401
        from web.server.tests.conftest import data_root as _  # noqa: F401

        app = create_app()
        with TestClient(app) as client:
            r = client.get("/api/chat/tools")
            tools = r.json()["tools"]
            for tool in tools:
                assert "name" in tool
                assert "description" in tool
                assert "method" in tool
                assert "path" in tool
                assert "parameters" in tool

    def test_excludes_chat_routes(self, data_root):
        app = create_app()
        with TestClient(app) as client:
            r = client.get("/api/chat/tools")
            tools = r.json()["tools"]
            paths = {t["path"] for t in tools}
            assert "/api/chat/tools" not in paths
            assert "/api/chat/proxy" not in paths


class TestProxyEndpoint:
    """POST /api/chat/proxy forwards requests."""

    def test_proxy_returns_422_without_body(self, data_root):
        app = create_app()
        with TestClient(app) as client:
            r = client.post("/api/chat/proxy", json={})
            assert r.status_code == 422

    def test_proxy_get_health(self, data_root, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock, patch
        import httpx

        app = create_app()
        with TestClient(app) as client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"status": "ok"}
            mock_response.headers = {"content-type": "application/json"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            monkeypatch.setattr(
                "web.server.chat_router.httpx.AsyncClient",
                lambda: mock_client,
            )

            r = client.post(
                "/api/chat/proxy",
                json={
                    "method": "GET",
                    "path": "/api/health",
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "ok"

    def test_proxy_passes_body_for_post(self, data_root, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock

        app = create_app()
        with TestClient(app) as client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"ticker": "NVDA"}
            mock_response.headers = {"content-type": "application/json"}
            mock_response.status_code = 201

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            monkeypatch.setattr(
                "web.server.chat_router.httpx.AsyncClient",
                lambda: mock_client,
            )

            r = client.post(
                "/api/chat/proxy",
                json={
                    "method": "POST",
                    "path": "/api/watchlist",
                    "body": {"ticker": "NVDA", "company_name": "NVIDIA"},
                },
            )
            assert r.status_code == 201
            # Verify httpx was called with the body
            call_kwargs = mock_client.request.call_args
            assert call_kwargs.kwargs["json"] == {"ticker": "NVDA", "company_name": "NVIDIA"}
