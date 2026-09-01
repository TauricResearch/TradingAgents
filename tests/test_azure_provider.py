"""Azure OpenAI provider.

Mirrors the coverage that the other LLM provider clients already have
(test_openai_compatible_provider.py, test_bedrock_provider.py): factory
routing, deployment-name env fallback, kwargs passthrough, and the
always-True validate_model() override (Azure accepts any deployed model
name since validation happens at deployment time, not at model-name time).
"""

import pytest

from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.validators import validate_model


@pytest.fixture(autouse=True)
def _api_version(monkeypatch):
    # AzureChatOpenAI requires an api_version / OPENAI_API_VERSION to
    # construct at all; set a stable one for every test in this module.
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-03-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example-resource.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key-123")


@pytest.mark.unit
def test_factory_routes_to_azure_client():
    client = create_llm_client(provider="azure", model="gpt-4o")
    assert type(client).__name__ == "AzureOpenAIClient"


@pytest.mark.unit
def test_deployment_name_falls_back_to_model(monkeypatch):
    # No AZURE_OPENAI_DEPLOYMENT_NAME set: azure_deployment should fall back
    # to the model name passed in.
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
    llm = create_llm_client(provider="azure", model="gpt-4o-mini").get_llm()
    assert llm.deployment_name == "gpt-4o-mini"


@pytest.mark.unit
def test_deployment_name_env_override(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "my-custom-deployment")
    llm = create_llm_client(provider="azure", model="gpt-4o").get_llm()
    assert llm.deployment_name == "my-custom-deployment"


@pytest.mark.unit
def test_passthrough_kwargs_forwarded():
    llm = create_llm_client(
        provider="azure", model="gpt-4o", temperature=0.3, max_retries=5
    ).get_llm()
    assert llm.temperature == 0.3
    assert llm.max_retries == 5


@pytest.mark.unit
def test_validate_model_always_true():
    # Azure deployments are validated at deploy time, not by model name, so
    # the client must accept any model string without prompting/erroring.
    assert validate_model("azure", "literally-anything") is True


@pytest.mark.unit
def test_api_key_env_name():
    assert get_api_key_env("azure") == "AZURE_OPENAI_API_KEY"
