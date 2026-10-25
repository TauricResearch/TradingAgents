"""Azure OpenAI client configuration."""

import pytest


@pytest.mark.unit
def test_azure_client_forwards_explicit_endpoint(monkeypatch):
    from tradingagents.llm_clients import azure_client as mod

    captured = {}
    monkeypatch.setattr(mod, "NormalizedAzureChatOpenAI", lambda **kwargs: captured.update(kwargs))

    mod.AzureOpenAIClient(
        "deployment", base_url="https://tier-resource.openai.azure.com/"
    ).get_llm()

    assert captured["azure_endpoint"] == "https://tier-resource.openai.azure.com/"
