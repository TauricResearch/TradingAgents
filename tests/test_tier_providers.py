"""Each model tier can name its own provider (#1440).

The quick tier (analysts, researchers, debaters, trader) and the deep tier
(research and portfolio managers) default to ``llm_provider``. A tier that names
another provider gets that provider's own settings and endpoint, never the main
provider's URL, and the run's settings and report say which provider each used.
"""

from unittest.mock import Mock

import pytest

from tradingagents import default_config
from tradingagents.llm_clients import factory


def _config(**overrides):
    config = {**default_config.DEFAULT_CONFIG, "llm_provider": "openai", "backend_url": "https://api.openai.com/v1",
              "quick_think_llm": "gpt-6-luna", "deep_think_llm": "gpt-6-sol",
              "openai_reasoning_effort": "low", "google_thinking_level": "high"}
    config.update(overrides)
    return config


def _captured(monkeypatch):
    made = []
    monkeypatch.setattr(factory, "create_llm_client",
                        lambda provider, model, base_url=None, **kw: made.append((provider, model, base_url, kw)))
    return made


@pytest.mark.unit
def test_a_tier_without_its_own_provider_uses_the_run_s(monkeypatch):
    made = _captured(monkeypatch)

    factory.create_tier_client(_config(), "deep")

    provider, model, base_url, kw = made[0]
    assert (provider, model, base_url) == ("openai", "gpt-6-sol", "https://api.openai.com/v1")
    assert kw["reasoning_effort"] == "low"


@pytest.mark.unit
def test_a_tier_on_another_provider_gets_that_provider_s_settings_and_not_the_main_url(monkeypatch):
    made = _captured(monkeypatch)

    factory.create_tier_client(_config(deep_think_provider="google", deep_think_llm="gemini-3.8-flash"), "deep")

    provider, model, base_url, kw = made[0]
    assert (provider, model) == ("google", "gemini-3.8-flash")
    assert base_url is None                       # the OpenAI URL must not follow it
    assert kw["thinking_level"] == "high" and "reasoning_effort" not in kw


@pytest.mark.unit
def test_a_tier_url_is_used_for_that_tier_only(monkeypatch):
    made = _captured(monkeypatch)
    config = _config(quick_think_provider="openai_compatible", quick_think_backend_url="http://localhost:8000/v1",
                     quick_think_llm="local-model")

    factory.create_tier_client(config, "quick")
    factory.create_tier_client(config, "deep")

    assert made[0][:3] == ("openai_compatible", "local-model", "http://localhost:8000/v1")
    assert made[1][:3] == ("openai", "gpt-6-sol", "https://api.openai.com/v1")


@pytest.mark.unit
def test_the_run_settings_and_report_name_each_tier_s_provider():
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.reporting import _header

    graph = object.__new__(TradingAgentsGraph)
    graph.selected_analysts = ("market",)
    graph.config = _config(deep_think_provider="anthropic", deep_think_llm="claude-opus-5-5")

    settings = graph.run_settings()
    assert settings["quick_think_provider"] == "openai" and settings["deep_think_provider"] == "anthropic"
    header = _header("NVDA", {}, settings)
    assert "deep anthropic claude-opus-5-5" in header and "quick openai gpt-6-luna" in header


@pytest.mark.unit
def test_the_tier_settings_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_DEEP_THINK_PROVIDER", "anthropic")
    monkeypatch.setenv("TRADINGAGENTS_QUICK_THINK_BACKEND_URL", "http://localhost:8000/v1")

    config = default_config.build_default_config()

    assert config["deep_think_provider"] == "anthropic"
    assert config["quick_think_backend_url"] == "http://localhost:8000/v1"
    assert config["quick_think_provider"] is None


@pytest.mark.unit
@pytest.mark.parametrize("tier", ["quick", "deep"])
@pytest.mark.parametrize("provider_from_env", [False, True], ids=["provider-menu", "provider-env"])
@pytest.mark.parametrize(
    "main_provider,other_provider,env_var,config_key,client_key,value",
    [
        ("openai", "google", "TRADINGAGENTS_GOOGLE_THINKING_LEVEL", "google_thinking_level", "thinking_level", "high"),
        ("openai", "anthropic", "TRADINGAGENTS_ANTHROPIC_EFFORT", "anthropic_effort", "effort", "low"),
        ("google", "openai", "TRADINGAGENTS_OPENAI_REASONING_EFFORT", "openai_reasoning_effort", "reasoning_effort", "low"),
    ],
)
def test_cli_preserves_other_tiers_thinking_settings(
    monkeypatch, tier, provider_from_env, main_provider, other_provider,
    env_var, config_key, client_key, value,
):
    """A menu-selected main provider must not clear the other tier's env setting."""
    import cli.run as cli_run
    import cli.selections as cli_selections

    for variable in default_config._ENV_OVERRIDES:
        monkeypatch.delenv(variable, raising=False)
    env = {
        "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
        "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "1",
        "TRADINGAGENTS_MAX_RISK_ROUNDS": "1",
        "TRADINGAGENTS_QUICK_THINK_LLM": "main-model",
        "TRADINGAGENTS_DEEP_THINK_LLM": "main-model",
        f"TRADINGAGENTS_{tier.upper()}_THINK_PROVIDER": other_provider,
        f"TRADINGAGENTS_{tier.upper()}_THINK_LLM": "tier-model",
        env_var: value,
    }
    if provider_from_env:
        env["TRADINGAGENTS_LLM_PROVIDER"] = main_provider
    for variable, setting in env.items():
        monkeypatch.setenv(variable, setting)
    defaults = default_config.build_default_config()
    monkeypatch.setattr(cli_selections, "DEFAULT_CONFIG", defaults)
    monkeypatch.setattr(cli_run, "DEFAULT_CONFIG", defaults)
    monkeypatch.setattr(cli_selections, "fetch_announcements", lambda: [])
    monkeypatch.setattr(cli_selections, "display_announcements", lambda *a: None)
    monkeypatch.setattr(cli_selections, "ensure_api_key", lambda provider: None)
    monkeypatch.setattr(cli_selections.console, "print", lambda *a, **k: None)
    provider_prompt = Mock(return_value=(main_provider, None))
    monkeypatch.setattr(cli_selections, "select_llm_provider", provider_prompt)
    openai_prompt = Mock(return_value="medium")
    google_prompt = Mock(return_value="minimal")
    monkeypatch.setattr(cli_selections, "ask_openai_reasoning_effort", openai_prompt)
    monkeypatch.setattr(cli_selections, "ask_gemini_thinking_config", google_prompt)

    selections = cli_selections.get_user_selections({
        "ticker": "NVDA", "date": "2026-09-01", "analysts": "market",
    })
    config = cli_run._build_run_config(selections, checkpoint=None)
    made = _captured(monkeypatch)
    factory.create_tier_client(config, tier)

    assert made[0][:2] == (other_provider, "tier-model")
    assert made[0][3].get(client_key) == value
    main_key, main_value, main_prompt = (
        ("openai_reasoning_effort", "medium", openai_prompt) if main_provider == "openai"
        else ("google_thinking_level", "minimal", google_prompt)
    )
    assert config[config_key] == value
    if provider_from_env:
        provider_prompt.assert_not_called()
        main_prompt.assert_not_called()
        assert config[main_key] is None
    else:
        provider_prompt.assert_called_once()
        main_prompt.assert_called_once()
        assert config[main_key] == main_value
