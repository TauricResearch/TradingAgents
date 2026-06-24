import asyncio
import os
import sys
import types
import warnings
from unittest import mock

import pytest


@pytest.mark.unit
def test_google_vertex_client_forwards_project_location_and_common_kwargs(monkeypatch):
    from tradingagents.llm_clients.google_vertex_client import GoogleVertexClient

    captured = {}

    class FakeChatVertexAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "tradingagents.llm_clients.google_vertex_client._vertex_class",
        lambda: FakeChatVertexAI,
    )

    client = GoogleVertexClient(
        "gemini-3.5-flash",
        project="vertex-project",
        location="us-central1",
        temperature=0.2,
        max_retries=3,
        callbacks=[object()],
    )

    assert client.get_llm().__class__ is FakeChatVertexAI
    assert captured["model"] == "gemini-3.5-flash"
    assert captured["project"] == "vertex-project"
    assert captured["location"] == "us-central1"
    assert captured["temperature"] == 0.2
    assert captured["max_retries"] == 3
    assert "google_api_key" not in captured


@pytest.mark.unit
def test_google_vertex_client_uses_google_cloud_env_fallbacks(monkeypatch):
    from tradingagents.llm_clients.google_vertex_client import GoogleVertexClient

    captured = {}

    class FakeChatVertexAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "tradingagents.llm_clients.google_vertex_client._vertex_class",
        lambda: FakeChatVertexAI,
    )
    monkeypatch.delenv("TRADINGAGENTS_VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_VERTEX_LOCATION", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "env-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west4")

    GoogleVertexClient("gemini-3.1-pro-preview").get_llm()

    assert captured["project"] == "env-project"
    assert captured["location"] == "europe-west4"


@pytest.mark.unit
def test_google_vertex_client_uses_tradingagents_env_fallbacks(monkeypatch):
    from tradingagents.llm_clients.google_vertex_client import GoogleVertexClient

    captured = {}

    class FakeChatVertexAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "tradingagents.llm_clients.google_vertex_client._vertex_class",
        lambda: FakeChatVertexAI,
    )
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)
    monkeypatch.setenv("TRADINGAGENTS_VERTEX_PROJECT", "framework-project")
    monkeypatch.setenv("TRADINGAGENTS_VERTEX_LOCATION", "asia-east1")

    GoogleVertexClient("gemini-3.5-flash").get_llm()

    assert captured["project"] == "framework-project"
    assert captured["location"] == "asia-east1"


@pytest.mark.unit
def test_google_vertex_client_defaults_location_to_global_with_warning(monkeypatch):
    from tradingagents.llm_clients.google_vertex_client import GoogleVertexClient

    captured = {}

    class FakeChatVertexAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "tradingagents.llm_clients.google_vertex_client._vertex_class",
        lambda: FakeChatVertexAI,
    )
    for env_var in (
        "TRADINGAGENTS_VERTEX_LOCATION",
        "GOOGLE_CLOUD_LOCATION",
        "VERTEXAI_LOCATION",
    ):
        monkeypatch.delenv(env_var, raising=False)

    with pytest.warns(RuntimeWarning, match="defaulting to 'global'"):
        GoogleVertexClient("gemini-3.5-flash").get_llm()

    assert captured["location"] == "global"


@pytest.mark.unit
def test_google_vertex_client_does_not_warn_when_location_is_configured(monkeypatch):
    from tradingagents.llm_clients.google_vertex_client import GoogleVertexClient

    captured = {}

    class FakeChatVertexAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "tradingagents.llm_clients.google_vertex_client._vertex_class",
        lambda: FakeChatVertexAI,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        GoogleVertexClient("gemini-3.5-flash", location="us-central1").get_llm()

    assert list(caught) == []
    assert captured["location"] == "us-central1"


@pytest.mark.unit
def test_google_vertex_client_maps_base_url_to_api_endpoint(monkeypatch):
    from tradingagents.llm_clients.google_vertex_client import GoogleVertexClient

    captured = {}

    class FakeChatVertexAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "tradingagents.llm_clients.google_vertex_client._vertex_class",
        lambda: FakeChatVertexAI,
    )

    GoogleVertexClient(
        "gemini-3.5-flash",
        base_url="https://us-central1-aiplatform.googleapis.com",
    ).get_llm()

    assert captured["api_endpoint"] == "https://us-central1-aiplatform.googleapis.com"
    assert "base_url" not in captured


@pytest.mark.unit
def test_google_vertex_factory_route(monkeypatch):
    from tradingagents.llm_clients.factory import create_llm_client
    from tradingagents.llm_clients.google_vertex_client import GoogleVertexClient

    client = create_llm_client(
        provider="google_vertex",
        model="gemini-3.5-flash",
        project="vertex-project",
        location="us-central1",
    )

    assert isinstance(client, GoogleVertexClient)
    assert client.kwargs["project"] == "vertex-project"
    assert client.kwargs["location"] == "us-central1"


@pytest.mark.unit
def test_google_vertex_factory_preserves_backend_url_as_base_url(monkeypatch):
    from tradingagents.llm_clients.factory import create_llm_client
    from tradingagents.llm_clients.google_vertex_client import GoogleVertexClient

    client = create_llm_client(
        provider="google_vertex",
        model="gemini-3.5-flash",
        base_url="https://private-aiplatform.example.com",
    )

    assert isinstance(client, GoogleVertexClient)
    assert client.base_url == "https://private-aiplatform.example.com"


@pytest.mark.unit
def test_google_vertex_has_no_api_key_prompt():
    from tradingagents.llm_clients.api_key_env import get_api_key_env

    assert get_api_key_env("google_vertex") is None


@pytest.mark.unit
def test_google_vertex_catalog_reuses_gemini_models():
    from tradingagents.llm_clients.model_catalog import get_model_options
    from tradingagents.llm_clients.validators import validate_model

    assert get_model_options("google_vertex", "quick") == get_model_options("google", "quick")
    assert validate_model("google_vertex", "gemini-3.5-flash") is True


@pytest.mark.unit
def test_trading_graph_forwards_vertex_project_location(monkeypatch):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    monkeypatch.setenv("TRADINGAGENTS_VERTEX_PROJECT", "config-project")
    monkeypatch.setenv("TRADINGAGENTS_VERTEX_LOCATION", "asia-northeast1")

    graph = object.__new__(TradingAgentsGraph)
    graph.config = {
        "llm_provider": "google_vertex",
        "google_thinking_level": "high",
        "vertex_project": os.environ["TRADINGAGENTS_VERTEX_PROJECT"],
        "vertex_location": os.environ["TRADINGAGENTS_VERTEX_LOCATION"],
        "temperature": None,
    }

    kwargs = graph._get_provider_kwargs()

    assert kwargs["project"] == "config-project"
    assert kwargs["location"] == "asia-northeast1"
    assert "thinking_level" not in kwargs


@pytest.mark.unit
def test_google_vertex_client_does_not_forward_thinking_level(monkeypatch):
    from tradingagents.llm_clients.google_vertex_client import GoogleVertexClient

    captured = {}

    class FakeChatVertexAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "tradingagents.llm_clients.google_vertex_client._vertex_class",
        lambda: FakeChatVertexAI,
    )

    GoogleVertexClient("gemini-3.5-flash", thinking_level="high").get_llm()

    assert "thinking_level" not in captured
    assert "thinking_budget" not in captured


@pytest.mark.unit
def test_google_vertex_ainvoke_normalizes_typed_content(monkeypatch):
    from tradingagents.llm_clients import google_vertex_client

    class FakeResponse:
        content = [
            {"type": "reasoning", "text": "hidden"},
            {"type": "text", "text": "visible"},
        ]

    class FakeChatVertexAI:
        async def ainvoke(self, input, config=None, **kwargs):
            return FakeResponse()

    fake_module = types.ModuleType("langchain_google_vertexai")
    fake_module.ChatVertexAI = FakeChatVertexAI
    monkeypatch.setitem(sys.modules, "langchain_google_vertexai", fake_module)
    monkeypatch.setattr(google_vertex_client, "_GOOGLE_VERTEX_CLASS", None)

    chat_cls = google_vertex_client._vertex_class()
    response = asyncio.run(chat_cls().ainvoke("hello"))

    assert response.content == "visible"


@pytest.mark.unit
def test_google_vertex_provider_default_url_is_sdk_default():
    from cli.utils import provider_default_url

    assert provider_default_url("google_vertex") is None


@pytest.mark.unit
def test_cli_does_not_prompt_gemini_thinking_for_google_vertex(monkeypatch):
    import cli.main as main

    fake_cfg = dict(main.DEFAULT_CONFIG)
    fake_cfg.update(
        {
            "google_thinking_level": None,
            "openai_reasoning_effort": None,
            "anthropic_effort": None,
        }
    )

    with mock.patch.dict(os.environ, {}, clear=False), \
         mock.patch.object(main, "DEFAULT_CONFIG", fake_cfg), \
         mock.patch.object(main, "fetch_announcements", return_value=None), \
         mock.patch.object(main, "display_announcements"), \
         mock.patch.object(main, "get_ticker", return_value="AAPL"), \
         mock.patch.object(main, "get_analysis_date", return_value="2026-06-23"), \
         mock.patch.object(main, "select_analysts", return_value=[]), \
         mock.patch.object(main, "select_research_depth", return_value=1), \
         mock.patch.object(main, "select_llm_provider", return_value=("google_vertex", None)), \
         mock.patch.object(main, "resolve_backend_url", return_value=None), \
         mock.patch.object(main, "ensure_api_key"), \
         mock.patch.object(main, "select_shallow_thinking_agent", return_value="gemini-3.5-flash"), \
         mock.patch.object(main, "select_deep_thinking_agent", return_value="gemini-3.1-pro-preview"), \
         mock.patch.object(main, "ask_output_language", return_value="English"), \
         mock.patch.object(main, "ask_gemini_thinking_config", return_value="high") as prompt_thinking:
        selections = main.get_user_selections()

    prompt_thinking.assert_not_called()
    assert selections["llm_provider"] == "google_vertex"
    assert selections["google_thinking_level"] is None
