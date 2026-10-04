"""Both interactive CLI flows validate and configure the providers their tiers use."""

import pytest
import typer

from cli import main, run, selections
from tradingagents import default_config
from tradingagents.llm_clients import factory


@pytest.fixture(params=[main, selections], ids=["fork", "upstream"])
def interactive_cli(request, monkeypatch):
    module = request.param
    for variable in default_config._ENV_OVERRIDES:
        monkeypatch.delenv(variable, raising=False)
    for key, value in {
        "llm_provider": "openai",
        "backend_url": None,
        "quick_think_provider": None,
        "deep_think_provider": None,
        "quick_think_llm": "gpt-5.4-mini",
        "deep_think_llm": "gpt-5.5",
        "google_thinking_level": None,
        "openai_reasoning_effort": "max",
        "anthropic_effort": "max",
    }.items():
        monkeypatch.setitem(default_config.DEFAULT_CONFIG, key, value)
    monkeypatch.setattr(module, "fetch_announcements", lambda: None)
    monkeypatch.setattr(module, "display_announcements", lambda *a: None)
    monkeypatch.setattr(module, "get_ticker", lambda: "NVDA")
    monkeypatch.setattr(module, "get_analysis_date", lambda: "2026-09-01")
    monkeypatch.setattr(module, "select_analysts", lambda *a: [])
    monkeypatch.setattr(module, "select_research_depth", lambda *a: 1)
    monkeypatch.setattr(module, "ask_output_language", lambda *a: "English")
    monkeypatch.setattr(module, "select_llm_provider", lambda *a: ("openai", None))
    monkeypatch.setattr(module, "select_shallow_thinking_agent", lambda *a: "gpt-5.4-mini")
    monkeypatch.setattr(module, "select_deep_thinking_agent", lambda *a: "gpt-5.5")
    monkeypatch.setattr(module, "ask_openai_reasoning_effort", lambda: "low")
    monkeypatch.setattr(module, "ask_anthropic_effort", lambda: "medium")
    monkeypatch.setattr(module, "ask_gemini_thinking_config", lambda: "minimal")
    checked = []
    monkeypatch.setattr(main, "ensure_api_key", checked.append)
    monkeypatch.setattr(selections, "ensure_api_key", checked.append)
    return module, checked


def _choose(module):
    return main.get_user_selections() if module is main else selections._prompt_selections({}, {})


@pytest.mark.unit
@pytest.mark.parametrize("provider_from_env", [False, True], ids=["provider-menu", "provider-env"])
def test_all_used_tier_provider_keys_are_checked_before_the_run(interactive_cli, monkeypatch, provider_from_env):
    module, checked = interactive_cli
    if provider_from_env:
        monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, "deep_think_provider", "anthropic")
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, "deep_think_llm", "claude-opus-4-6")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_THINK_LLM", "claude-opus-4-6")

    _choose(module)

    assert checked == ["openai", "anthropic"]


@pytest.mark.unit
def test_a_provider_unused_by_either_tier_does_not_require_a_key(interactive_cli, monkeypatch):
    module, checked = interactive_cli
    for tier in ("quick", "deep"):
        monkeypatch.setitem(default_config.DEFAULT_CONFIG, f"{tier}_think_provider", "anthropic")
        monkeypatch.setitem(default_config.DEFAULT_CONFIG, f"{tier}_think_llm", "claude-opus-4-6")
        monkeypatch.setenv(f"TRADINGAGENTS_{tier.upper()}_THINK_LLM", "claude-opus-4-6")

    _choose(module)

    assert checked == ["anthropic"]


@pytest.mark.unit
def test_a_cross_provider_tier_without_its_own_model_stops_before_key_or_model_prompts(
    interactive_cli, monkeypatch, capsys,
):
    module, checked = interactive_cli
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, "deep_think_provider", "anthropic")

    def unexpected_prompt(*a):
        pytest.fail("selected a main-provider model for an Anthropic tier")

    monkeypatch.setattr(module, "select_shallow_thinking_agent", unexpected_prompt)
    monkeypatch.setattr(module, "select_deep_thinking_agent", unexpected_prompt)

    with pytest.raises(typer.Exit) as error:
        _choose(module)

    assert error.value.exit_code == 1
    assert "TRADINGAGENTS_DEEP_THINK_LLM" in capsys.readouterr().out
    assert checked == []


@pytest.mark.unit
@pytest.mark.parametrize("main_provider, tier_provider, setting, variable, expected_kwarg", [
    ("openai", "anthropic", "anthropic_effort", "TRADINGAGENTS_ANTHROPIC_EFFORT", "effort"),
    ("anthropic", "google", "google_thinking_level", "TRADINGAGENTS_GOOGLE_THINKING_LEVEL", "thinking_level"),
    ("google", "openai", "openai_reasoning_effort", "TRADINGAGENTS_OPENAI_REASONING_EFFORT", "reasoning_effort"),
])
def test_an_interactive_main_provider_preserves_the_other_tiers_explicit_thinking_setting(
    interactive_cli, monkeypatch, main_provider, tier_provider, setting, variable, expected_kwarg,
):
    module, _ = interactive_cli
    monkeypatch.setattr(module, "select_llm_provider", lambda *a: (main_provider, None))
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, "deep_think_provider", tier_provider)
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, "deep_think_llm", "secondary-model")
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, setting, "high")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_THINK_LLM", "secondary-model")
    monkeypatch.setenv(variable, "high")
    made = []
    monkeypatch.setattr(factory, "create_llm_client", lambda **kw: made.append(kw))

    chosen = _choose(module)
    config = (main if module is main else run)._build_run_config(chosen, checkpoint=None)
    factory.create_tier_client(config, "deep")

    assert made[0]["provider"] == tier_provider
    assert made[0][expected_kwarg] == "high"


@pytest.mark.unit
@pytest.mark.parametrize("quick_provider, deep_provider, expected", [
    (None, "anthropic", ["openai", "anthropic"]),
    ("anthropic", "ANTHROPIC", ["anthropic"]),
])
def test_headless_explicit_models_check_the_resolved_tier_keys_without_environment_model_variables(
    monkeypatch, quick_provider, deep_provider, expected,
):
    for variable in default_config._ENV_OVERRIDES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, "quick_think_provider", quick_provider)
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, "deep_think_provider", deep_provider)
    checked = []
    monkeypatch.setattr(selections, "ensure_api_key", checked.append)
    chosen = {
        "llm_provider": "openai", "backend_url": None, "research_depth": 1,
        "shallow_thinker": "explicit-quick-model", "deep_thinker": "explicit-deep-model",
    }

    config = main._build_run_config(chosen, checkpoint=None)
    selections.ensure_run_provider_keys(config)

    assert config["quick_think_llm"] == "explicit-quick-model"
    assert config["deep_think_llm"] == "explicit-deep-model"
    assert checked == expected


@pytest.mark.unit
@pytest.mark.parametrize("quick_provider, deep_provider, expected", [
    (None, "anthropic", ["openai", "anthropic"]),
    ("anthropic", "anthropic", ["anthropic"]),
])
def test_headless_run_checks_tier_keys_before_constructing_the_graph(
    monkeypatch, quick_provider, deep_provider, expected,
):
    from cli.models import AnalystType

    class GraphReached(Exception):
        pass

    for variable in default_config._ENV_OVERRIDES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, "quick_think_provider", quick_provider)
    monkeypatch.setitem(default_config.DEFAULT_CONFIG, "deep_think_provider", deep_provider)
    checked = []
    monkeypatch.setattr(selections, "ensure_api_key", checked.append)

    def construct_graph(*args, **kwargs):
        assert checked == expected
        raise GraphReached

    monkeypatch.setattr(main, "TradingAgentsGraph", construct_graph)
    chosen = {
        "ticker": "NVDA", "analysis_date": "2026-01-09", "asset_type": "stock",
        "analysts": [AnalystType.MARKET], "llm_provider": "openai",
        "backend_url": None, "research_depth": 1,
        "shallow_thinker": "explicit-quick-model", "deep_thinker": "explicit-deep-model",
    }

    with pytest.raises(GraphReached):
        main.run_analysis(selections=chosen, post_save=True, post_display=False)
