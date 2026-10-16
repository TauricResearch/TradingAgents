"""OpenAI ``service_tier`` is configurable from the environment (#1487).

Scheduled sweeps don't need fast responses, so users can pick the cheaper
Flex tier with ``TRADINGAGENTS_OPENAI_SERVICE_TIER=flex`` instead of editing
the code. Follows the same pattern as ``openai_reasoning_effort``.
"""

import pytest

from tradingagents import default_config as default_config_module
from tradingagents.llm_clients import factory
from tradingagents.llm_clients.openai_client import OpenAIClient


def _config_with_env(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return default_config_module.build_default_config()


@pytest.mark.unit
def test_service_tier_env_override(monkeypatch):
    config = _config_with_env(monkeypatch, TRADINGAGENTS_OPENAI_SERVICE_TIER="flex")
    assert config["openai_service_tier"] == "flex"


@pytest.mark.unit
def test_service_tier_defaults_to_none(monkeypatch):
    config = _config_with_env(monkeypatch)
    assert config["openai_service_tier"] is None


@pytest.mark.unit
def test_build_llm_kwargs_forwards_service_tier_for_openai():
    kwargs = factory.build_llm_kwargs({"llm_provider": "openai", "openai_service_tier": "flex"})
    assert kwargs["service_tier"] == "flex"


@pytest.mark.unit
def test_build_llm_kwargs_omits_unset_service_tier():
    kwargs = factory.build_llm_kwargs({"llm_provider": "openai", "openai_service_tier": None})
    assert "service_tier" not in kwargs


@pytest.mark.unit
def test_build_llm_kwargs_omits_service_tier_for_other_providers():
    kwargs = factory.build_llm_kwargs({"llm_provider": "google", "openai_service_tier": "flex"})
    assert "service_tier" not in kwargs


@pytest.mark.unit
def test_openai_client_reaches_chat_openai(monkeypatch):
    # A fake key lets get_llm() construct the client without a network call.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    llm = OpenAIClient("gpt-6-luna", provider="openai", service_tier="flex").get_llm()
    assert getattr(llm, "service_tier", None) == "flex"
