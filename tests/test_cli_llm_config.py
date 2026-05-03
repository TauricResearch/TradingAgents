import cli.main
from cli.llm_config import LLMConfigOverrides, ResolvedLLMConfig, resolve_llm_config
from typer.testing import CliRunner

from cli.main import app


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


def test_analyze_accepts_llm_config_options(monkeypatch):
    runner = CliRunner()
    captured = {}

    def fake_run_analysis(*, checkpoint, llm_overrides):
        captured["checkpoint"] = checkpoint
        captured["llm_overrides"] = llm_overrides

    monkeypatch.setattr("cli.main.run_analysis", fake_run_analysis)

    result = runner.invoke(
        app,
        [
            "--llm-provider",
            "openai",
            "--quick-model",
            "mercury",
            "--deep-model",
            "mercury",
            "--backend-url",
            "https://api.inceptionlabs.ai/v1",
        ],
    )

    assert result.exit_code == 0
    assert captured["llm_overrides"].provider == "openai"
    assert captured["llm_overrides"].quick_model == "mercury"
    assert captured["llm_overrides"].deep_model == "mercury"
    assert captured["llm_overrides"].backend_url == "https://api.inceptionlabs.ai/v1"


def test_get_user_selections_skips_llm_prompts_when_config_complete(monkeypatch):
    monkeypatch.setattr("cli.main.fetch_announcements", lambda: [])
    monkeypatch.setattr("cli.main.display_announcements", lambda console, announcements: None)
    monkeypatch.setattr("cli.main.get_ticker", lambda: "SPY")
    monkeypatch.setattr("cli.main.get_analysis_date", lambda: "2026-05-01")
    monkeypatch.setattr("cli.main.ask_output_language", lambda: "English")
    monkeypatch.setattr("cli.main.select_analysts", lambda: [])
    monkeypatch.setattr("cli.main.select_research_depth", lambda: 1)
    monkeypatch.setattr("cli.main.ask_openai_reasoning_effort", lambda: None)

    monkeypatch.setattr(
        "cli.main.select_llm_provider",
        lambda: pytest.fail("provider prompt should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.select_shallow_thinking_agent",
        lambda provider: pytest.fail("quick model prompt should be skipped"),
    )
    monkeypatch.setattr(
        "cli.main.select_deep_thinking_agent",
        lambda provider: pytest.fail("deep model prompt should be skipped"),
    )

    selections = cli.main.get_user_selections(
        ResolvedLLMConfig(
            provider="openai",
            quick_model="mercury",
            deep_model="mercury",
            backend_url="https://api.inceptionlabs.ai/v1",
            openai_reasoning_effort=None,
            google_thinking_level=None,
            anthropic_effort=None,
        )
    )

    assert selections["llm_provider"] == "openai"
    assert selections["shallow_thinker"] == "mercury"
    assert selections["deep_thinker"] == "mercury"
    assert selections["backend_url"] == "https://api.inceptionlabs.ai/v1"
