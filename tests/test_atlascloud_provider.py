"""Atlas Cloud provider integration across the shared provider registries."""

import pytest

from cli.utils import provider_default_url
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.capabilities import get_capabilities
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.llm_clients.openai_client import (
    OPENAI_COMPATIBLE_PROVIDERS,
    DeepSeekChatOpenAI,
    is_openai_compatible,
)
from tradingagents.llm_clients.validators import validate_model

MODEL = "deepseek-ai/deepseek-v4-pro"


@pytest.mark.unit
def test_atlascloud_registry_contract():
    spec = OPENAI_COMPATIBLE_PROVIDERS["atlascloud"]

    assert is_openai_compatible("atlascloud")
    assert spec.base_url == "https://api.atlascloud.ai/v1"
    assert spec.chat_class is DeepSeekChatOpenAI
    assert get_api_key_env("atlascloud") == "ATLASCLOUD_API_KEY"
    assert provider_default_url("atlascloud") == "https://api.atlascloud.ai/v1"


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["quick", "deep"])
def test_atlascloud_model_catalog(mode):
    options = get_model_options("atlascloud", mode)

    assert any(value == MODEL for _, value in options)
    assert validate_model("atlascloud", MODEL)


@pytest.mark.unit
def test_atlascloud_uses_deepseek_tool_calling_capabilities():
    capabilities = get_capabilities(MODEL)

    assert capabilities.supports_tool_choice is False
    assert capabilities.requires_reasoning_content_roundtrip is True


@pytest.mark.unit
def test_atlascloud_client_resolves_endpoint_and_key(monkeypatch):
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "test-key")

    llm = create_llm_client(provider="atlascloud", model=MODEL).get_llm()

    assert type(llm).__name__ == "DeepSeekChatOpenAI"
    assert str(llm.openai_api_base) == "https://api.atlascloud.ai/v1"
    key = (
        llm.openai_api_key.get_secret_value()
        if hasattr(llm.openai_api_key, "get_secret_value")
        else llm.openai_api_key
    )
    assert key == "test-key"
    assert getattr(llm, "use_responses_api", False) in (False, None)
