"""Configurable LLM client request timeout."""
import importlib
import sys
import types

import pytest

import tradingagents.default_config as default_config_module
from tradingagents.llm_clients.factory import build_llm_kwargs, create_llm_client


@pytest.mark.unit
def test_timeout_is_forwarded_to_client_when_set():
    client = create_llm_client(
        "openai", "gpt-6-luna", **build_llm_kwargs({"llm_provider": "openai", "llm_timeout": "12.5"})
    )
    assert client.kwargs["timeout"] == 12.5


@pytest.mark.unit
def test_timeout_is_not_forwarded_when_unset():
    client = create_llm_client(
        "openai", "gpt-6-luna", **build_llm_kwargs({"llm_provider": "openai", "llm_timeout": None})
    )
    assert "timeout" not in client.kwargs


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["openai", "anthropic", "google", "bedrock"])
def test_timeout_builds_provider_timeout_kwarg(provider):
    assert build_llm_kwargs({"llm_provider": provider, "llm_timeout": "12.5"})["timeout"] == 12.5


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
def test_bedrock_timeout_maps_to_botocore_config(monkeypatch):
    import tradingagents.llm_clients.bedrock_client as bedrock_client

    class FakeConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    botocore = types.ModuleType("botocore")
    config = types.ModuleType("botocore.config")
    config.Config = FakeConfig
    monkeypatch.setitem(sys.modules, "botocore", botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", config)

    captured = {}

    class FakeChat:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(bedrock_client, "_bedrock_class", lambda: FakeChat)
    create_llm_client("bedrock", "model", timeout=12.5).get_llm()
    assert captured["config"].kwargs == {"connect_timeout": 12.5, "read_timeout": 12.5}
