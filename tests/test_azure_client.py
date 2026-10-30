"""Azure OpenAI takes the run's settings like every other provider."""

from __future__ import annotations

import pytest

from tradingagents.llm_clients.factory import create_llm_client


@pytest.fixture(autouse=True)
def _azure_env(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://from-env.openai.azure.com/")
    monkeypatch.setenv("OPENAI_API_VERSION", "2025-03-01-preview")
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)


@pytest.mark.unit
def test_the_output_token_cap_reaches_the_deployment():
    llm = create_llm_client("azure", "gpt-5.5", max_tokens=1234).get_llm()
    assert llm.max_tokens == 1234


@pytest.mark.unit
def test_an_explicit_endpoint_wins_over_the_environment():
    llm = create_llm_client("azure", "gpt-5.5", base_url="https://deep.openai.azure.com/").get_llm()
    assert llm.azure_endpoint == "https://deep.openai.azure.com/"
    assert create_llm_client("azure", "gpt-5.5").get_llm().azure_endpoint == "https://from-env.openai.azure.com/"
