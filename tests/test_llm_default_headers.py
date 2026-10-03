"""Configurable extra request headers on LLM calls.

``llm_default_headers`` lets a run send its own headers (for example a run id)
to whatever sits in front of the model, so a gateway or proxy can attribute or
cap the cost of one analysis. Forwarded to the OpenAI-compatible, Azure and
Anthropic clients; providers without header support ignore it.
"""
from __future__ import annotations

import pytest

import tradingagents.default_config as default_config_module
from tradingagents.llm_clients import anthropic_client, azure_client, openai_client
from tradingagents.llm_clients.factory import build_llm_kwargs, create_llm_client

HEADERS = {"X-Run-Id": "analysis-001"}


@pytest.mark.unit
def test_default_is_none():
    assert default_config_module.DEFAULT_CONFIG["llm_default_headers"] is None


@pytest.mark.unit
def test_not_forwarded_when_unset():
    assert "default_headers" not in build_llm_kwargs({"llm_provider": "openai"})


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["openai", "anthropic", "openai_compatible", "google"])
def test_forwarded_when_set(provider):
    kwargs = build_llm_kwargs({"llm_provider": provider, "llm_default_headers": HEADERS})
    assert kwargs["default_headers"] == HEADERS


@pytest.mark.unit
def test_values_are_strings():
    kwargs = build_llm_kwargs({"llm_provider": "openai", "llm_default_headers": {"X-Budget": 0.5}})
    assert kwargs["default_headers"] == {"X-Budget": "0.5"}


@pytest.mark.unit
def test_non_dict_fails_loudly():
    with pytest.raises(ValueError, match="dict"):
        build_llm_kwargs({"llm_provider": "openai", "llm_default_headers": "X-Run-Id: 1"})


@pytest.mark.unit
def test_clients_that_support_headers_accept_the_kwarg():
    assert "default_headers" in openai_client._PASSTHROUGH_KWARGS
    assert "default_headers" in anthropic_client._PASSTHROUGH_KWARGS
    assert "default_headers" in azure_client._PASSTHROUGH_KWARGS


@pytest.mark.unit
def test_openai_compatible_chat_model_carries_the_headers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = create_llm_client(
        provider="openai", model="gpt-4o-mini", base_url="http://127.0.0.1:8000/v1",
        default_headers=HEADERS,
    )
    llm = client.get_llm()
    assert llm.default_headers == HEADERS
