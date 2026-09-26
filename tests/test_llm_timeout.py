"""Configurable LLM client request timeout."""
import importlib

import pytest

import tradingagents.default_config as default_config_module
from tradingagents.llm_clients.factory import build_llm_kwargs, create_llm_client


@pytest.mark.unit
def test_timeout_reaches_the_openai_http_client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    kwargs = build_llm_kwargs({"llm_provider": "openai", "llm_timeout": "12.5"})
    llm = create_llm_client("openai", "gpt-6-luna", **kwargs).get_llm()
    assert llm.root_client.timeout == 12.5
    assert llm.root_async_client.timeout == 12.5


@pytest.mark.unit
def test_timeout_reaches_google_client_constructor():
    from tradingagents.llm_clients.google_client import GoogleClient

    kwargs = build_llm_kwargs({"llm_provider": "google", "llm_timeout": "12.5"})
    llm = GoogleClient("gemini-3.5-flash", api_key="test", **kwargs).get_llm()
    assert llm.timeout == 12.5


@pytest.mark.unit
def test_timeout_is_not_forwarded_when_unset():
    client = create_llm_client(
        "openai", "gpt-6-luna", **build_llm_kwargs({"llm_provider": "openai", "llm_timeout": None})
    )
    assert "timeout" not in client.kwargs


def _reload_with_env(monkeypatch, **overrides):
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(default_config_module)


@pytest.mark.unit
def test_timeout_env_override(monkeypatch):
    dc = _reload_with_env(monkeypatch, TRADINGAGENTS_LLM_TIMEOUT="12.5")
    assert dc.DEFAULT_CONFIG["llm_timeout"] == "12.5"
    assert build_llm_kwargs(dc.DEFAULT_CONFIG)["timeout"] == 12.5


@pytest.mark.unit
def test_bedrock_forwards_timeout_alongside_max_retries(monkeypatch):
    import tradingagents.llm_clients.bedrock_client as bedrock_client

    captured = {}

    class FakeChat:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(bedrock_client, "_bedrock_class", lambda: FakeChat)
    create_llm_client("bedrock", "model", timeout=12.5, max_retries=3).get_llm()
    assert captured["timeout"] == 13
    assert captured["max_retries"] == 3
