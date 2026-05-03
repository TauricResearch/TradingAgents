from cli.llm_config import LLMConfigOverrides, resolve_llm_config


LLM_CONFIG_ENV_VARS = (
    "TRADINGAGENTS_LLM_PROVIDER",
    "TRADINGAGENTS_QUICK_MODEL",
    "TRADINGAGENTS_DEEP_MODEL",
    "TRADINGAGENTS_BACKEND_URL",
    "TRADINGAGENTS_OPENAI_REASONING_EFFORT",
    "TRADINGAGENTS_GOOGLE_THINKING_LEVEL",
    "TRADINGAGENTS_ANTHROPIC_EFFORT",
)


def clear_llm_config_env(monkeypatch):
    for env_var in LLM_CONFIG_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)


def test_env_resolves_openai_compatible_custom_model(monkeypatch):
    clear_llm_config_env(monkeypatch)
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TRADINGAGENTS_BACKEND_URL", "https://api.inceptionlabs.ai/v1")
    monkeypatch.setenv("TRADINGAGENTS_QUICK_MODEL", "mercury")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_MODEL", "mercury")

    resolved = resolve_llm_config(LLMConfigOverrides())

    assert resolved.provider == "openai"
    assert resolved.backend_url == "https://api.inceptionlabs.ai/v1"
    assert resolved.quick_model == "mercury"
    assert resolved.deep_model == "mercury"
    assert resolved.is_complete is True


def test_cli_overrides_env(monkeypatch):
    clear_llm_config_env(monkeypatch)
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("TRADINGAGENTS_QUICK_MODEL", "claude-3-5-haiku-latest")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_MODEL", "claude-3-7-sonnet-latest")

    resolved = resolve_llm_config(
        LLMConfigOverrides(
            provider="openai",
            quick_model="gpt-5.4-mini",
            deep_model="gpt-5.4",
            backend_url="https://api.openai.com/v1",
        )
    )

    assert resolved.provider == "openai"
    assert resolved.quick_model == "gpt-5.4-mini"
    assert resolved.deep_model == "gpt-5.4"
    assert resolved.backend_url == "https://api.openai.com/v1"


def test_partial_config_is_not_complete(monkeypatch):
    clear_llm_config_env(monkeypatch)
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TRADINGAGENTS_QUICK_MODEL", "mercury")

    resolved = resolve_llm_config(LLMConfigOverrides())

    assert resolved.provider == "openai"
    assert resolved.quick_model == "mercury"
    assert resolved.deep_model is None
    assert resolved.is_complete is False
