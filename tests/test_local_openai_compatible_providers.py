"""Tests for local OpenAI-compatible provider plumbing."""

from __future__ import annotations

import importlib

import pytest

from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.llm_clients.validators import validate_model


def _reload_openai_client():
    import tradingagents.llm_clients.openai_client as mod
    return importlib.reload(mod)


@pytest.mark.parametrize(
    "provider,default_url",
    [
        ("lm-studio", "http://localhost:8000/v1"),
        ("llama-cpp", "http://localhost:8001/v1"),
    ],
)
def test_local_provider_default_base_urls(monkeypatch, provider, default_url):
    monkeypatch.delenv("LM_STUDIO_BASE_URL", raising=False)
    monkeypatch.delenv("LLAMA_CPP_BASE_URL", raising=False)
    mod = _reload_openai_client()

    assert mod._resolve_provider_base_url(provider) == default_url


def test_local_provider_base_url_env_overrides_are_call_time(monkeypatch):
    mod = _reload_openai_client()
    monkeypatch.setenv("LM_STUDIO_BASE_URL", "http://studio-host:9000/v1")
    monkeypatch.setenv("LLAMA_CPP_BASE_URL", "http://llama-host:9001/v1")

    assert mod._resolve_provider_base_url("lm-studio") == "http://studio-host:9000/v1"
    assert mod._resolve_provider_base_url("llama-cpp") == "http://llama-host:9001/v1"


def test_explicit_local_base_url_overrides_env(monkeypatch):
    monkeypatch.setenv("LM_STUDIO_BASE_URL", "http://env-studio:8000/v1")
    mod = _reload_openai_client()

    client = mod.OpenAIClient(
        model="local-model",
        provider="lm-studio",
        base_url="http://explicit-studio:8000/v1",
    )
    llm = client.get_llm()

    assert "explicit-studio" in str(llm.openai_api_base)
    assert "env-studio" not in str(llm.openai_api_base)


@pytest.mark.parametrize("provider", ["lm-studio", "llama-cpp"])
def test_local_providers_use_openai_compatible_client(provider):
    client = create_llm_client(provider=provider, model="local-model")

    assert client.__class__.__name__ == "OpenAIClient"
    assert client.provider == provider


@pytest.mark.parametrize("provider", ["lm-studio", "llama-cpp"])
def test_local_providers_do_not_require_api_keys(provider):
    assert get_api_key_env(provider) is None


@pytest.mark.parametrize("provider", ["lm-studio", "llama-cpp"])
def test_local_providers_accept_custom_model_ids(provider):
    assert validate_model(provider, "anything-loaded-locally")


@pytest.mark.parametrize("provider", ["lm-studio", "llama-cpp"])
def test_local_provider_model_catalog_prompts_for_custom_model(provider):
    for mode in ("quick", "deep"):
        entries = get_model_options(provider, mode)
        assert entries == [("Custom local model ID", "custom")]


def test_cli_provider_selection_uses_local_runtime_env(monkeypatch):
    import cli.utils as cli_utils

    captured = {}

    class Prompt:
        def ask(self):
            return ("lm-studio", "http://studio-host:9000/v1")

    def fake_select(message, choices, **kwargs):
        captured["choices"] = choices
        return Prompt()

    monkeypatch.setenv("LM_STUDIO_BASE_URL", "http://studio-host:9000/v1")
    monkeypatch.setattr(cli_utils.questionary, "select", fake_select)

    provider, url = cli_utils.select_llm_provider()

    assert provider == "lm-studio"
    assert url == "http://studio-host:9000/v1"
    assert ("lm-studio", "http://studio-host:9000/v1") in [
        choice.value for choice in captured["choices"]
    ]
