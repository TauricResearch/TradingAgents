"""Programmatic credentials do not require a duplicate environment setting."""

import pytest

from tradingagents.llm_clients import create_llm_client


@pytest.mark.unit
@pytest.mark.parametrize(
    "provider,model,env_var",
    [
        ("openai", "gpt-6-sol", "OPENAI_API_KEY"),
        ("deepseek", "deepseek-v4-flash", "DEEPSEEK_API_KEY"),
        ("openrouter", "openai/gpt-6-sol", "OPENROUTER_API_KEY"),
    ],
)
def test_explicit_key_works_without_provider_environment(monkeypatch, provider, model, env_var):
    monkeypatch.delenv(env_var, raising=False)
    llm = create_llm_client(provider, model, api_key="explicit-test-key").get_llm()
    assert llm.openai_api_key.get_secret_value() == "explicit-test-key"


@pytest.mark.unit
def test_explicit_key_still_overrides_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "environment-test-key")
    llm = create_llm_client("openai", "gpt-6-sol", api_key="explicit-test-key").get_llm()
    assert llm.openai_api_key.get_secret_value() == "explicit-test-key"


@pytest.mark.unit
def test_missing_key_still_reports_the_provider_variable(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        create_llm_client("openrouter", "gpt-6-sol").get_llm()
