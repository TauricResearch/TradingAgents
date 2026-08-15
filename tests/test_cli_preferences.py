"""Tests for persisted CLI preference behavior."""

import io
import json
import os
import stat

import pytest
import questionary
import typer

import cli.main as m
import cli.preferences as preferences
from cli.utils import provider_default_url
from tradingagents.llm_clients.model_catalog import get_model_options


def _valid_preferences(**overrides):
    prefs = {
        "llm_provider": "openai",
        "backend_url": "https://api.openai.com/v1",
        "quick_think_llm": "gpt-5.4-mini",
        "deep_think_llm": "gpt-5.5",
        "output_language": "English",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "google_thinking_level": None,
        "openai_reasoning_effort": None,
        "anthropic_effort": None,
    }
    prefs.update(overrides)
    return prefs


def test_saved_preferences_are_utf8_and_private(monkeypatch, tmp_path):
    preferences_home = tmp_path / "tradingagents"
    preferences_path = preferences_home / "preferences.json"
    monkeypatch.setattr(preferences, "_TRADINGAGENTS_HOME", preferences_home)
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", preferences_path)

    assert preferences.save_preferences(
        _valid_preferences(
            output_language="中文",
            OPENAI_API_KEY="must-not-be-persisted",
        )
    )

    saved = json.loads(preferences_path.read_text(encoding="utf-8"))
    assert saved["output_language"] == "中文"
    assert "OPENAI_API_KEY" not in saved
    if os.name != "nt":
        assert stat.S_IMODE(preferences_path.stat().st_mode) == 0o600


def test_failed_preferences_replace_preserves_previous_file(monkeypatch, tmp_path):
    preferences_home = tmp_path / "tradingagents"
    preferences_path = preferences_home / "preferences.json"
    monkeypatch.setattr(preferences, "_TRADINGAGENTS_HOME", preferences_home)
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", preferences_path)

    assert preferences.save_preferences(_valid_preferences(llm_provider="openai"))

    def fail_replace(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(preferences.os, "replace", fail_replace)

    assert not preferences.save_preferences(_valid_preferences(llm_provider="deepseek"))
    assert preferences.load_preferences()["llm_provider"] == "openai"


def test_save_preferences_rejects_incomplete_bundle(monkeypatch, tmp_path):
    preferences_home = tmp_path / "tradingagents"
    preferences_path = preferences_home / "preferences.json"
    monkeypatch.setattr(preferences, "_TRADINGAGENTS_HOME", preferences_home)
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", preferences_path)

    assert not preferences.save_preferences({"llm_provider": "openai"})
    assert not preferences_path.exists()


@pytest.mark.parametrize("provider", ["openrouter", "azure"])
def test_dynamic_model_providers_can_be_saved(monkeypatch, tmp_path, provider):
    preferences_home = tmp_path / "tradingagents"
    preferences_path = preferences_home / "preferences.json"
    monkeypatch.setattr(preferences, "_TRADINGAGENTS_HOME", preferences_home)
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", preferences_path)

    assert preferences.save_preferences(
        _valid_preferences(
            llm_provider=provider,
            backend_url="https://provider.example/v1",
            quick_think_llm="provider-quick-deployment",
            deep_think_llm="provider-deep-deployment",
        )
    )
    assert preferences.load_preferences_result().status == "valid"


def test_load_preferences_ignores_invalid_known_values(monkeypatch, tmp_path):
    preferences_home = tmp_path / "tradingagents"
    preferences_path = preferences_home / "preferences.json"
    preferences_home.mkdir()
    monkeypatch.setattr(preferences, "_TRADINGAGENTS_HOME", preferences_home)
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", preferences_path)
    preferences_path.write_text(
        json.dumps(
            {
                "_version": 1,
                "llm_provider": "deepseek",
                "output_language": 42,
                "max_debate_rounds": "many",
                "max_risk_discuss_rounds": 0,
            }
        ),
        encoding="utf-8",
    )

    result = preferences.load_preferences_result()

    assert result.status == "invalid"
    assert result.preferences is None
    assert preferences.load_preferences() is None


def test_config_show_explains_pre_run_configuration(monkeypatch, capsys):
    monkeypatch.setattr(
        m,
        "load_preferences_result",
        lambda: preferences.PreferenceLoadResult("missing"),
    )

    m.config_show()

    output = capsys.readouterr().out
    assert "tradingagents config set" in output
    assert "saved after the first run" not in output


def test_load_preferences_handles_invalid_version(monkeypatch, tmp_path):
    preferences_home = tmp_path / "tradingagents"
    preferences_path = preferences_home / "preferences.json"
    preferences_home.mkdir()
    monkeypatch.setattr(preferences, "_TRADINGAGENTS_HOME", preferences_home)
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", preferences_path)
    preferences_path.write_text(
        json.dumps({"_version": "future", "llm_provider": "openai"}),
        encoding="utf-8",
    )

    assert preferences.load_preferences() is None


def test_load_preferences_handles_invalid_utf8(monkeypatch, tmp_path):
    preferences_home = tmp_path / "tradingagents"
    preferences_path = preferences_home / "preferences.json"
    preferences_home.mkdir()
    monkeypatch.setattr(preferences, "_TRADINGAGENTS_HOME", preferences_home)
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", preferences_path)
    preferences_path.write_bytes(b"\xff\xfe")

    assert preferences.load_preferences() is None


def test_partial_preferences_are_not_reusable(monkeypatch, tmp_path):
    preferences_home = tmp_path / "tradingagents"
    preferences_path = preferences_home / "preferences.json"
    preferences_home.mkdir()
    monkeypatch.setattr(preferences, "_TRADINGAGENTS_HOME", preferences_home)
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", preferences_path)
    preferences_path.write_text(
        json.dumps({"_version": 1, "llm_provider": "deepseek"}),
        encoding="utf-8",
    )

    result = preferences.load_preferences_result()

    assert result.status == "invalid"
    assert result.preferences is None
    assert preferences.load_preferences() is None


def test_future_preferences_are_distinguished_from_missing(monkeypatch, tmp_path):
    preferences_home = tmp_path / "tradingagents"
    preferences_path = preferences_home / "preferences.json"
    preferences_home.mkdir()
    monkeypatch.setattr(preferences, "_TRADINGAGENTS_HOME", preferences_home)
    monkeypatch.setattr(preferences, "PREFERENCES_PATH", preferences_path)
    original = json.dumps({"_version": 99, "llm_provider": "openai"})
    preferences_path.write_text(original, encoding="utf-8")

    result = preferences.load_preferences_result()

    assert result.status == "future"
    assert result.preferences is None
    assert preferences_path.read_text(encoding="utf-8") == original


def test_saved_debate_and_risk_rounds_are_restored_independently(monkeypatch):
    prefs = {
        "llm_provider": "openai",
        "quick_think_llm": "gpt-5.4-mini",
        "deep_think_llm": "gpt-5.5",
        "output_language": "English",
        "max_debate_rounds": 2,
        "max_risk_discuss_rounds": 4,
    }

    selections = preferences.preferences_to_selections(prefs, defaults=m.DEFAULT_CONFIG)

    assert selections["max_debate_rounds"] == 2
    assert selections["max_risk_discuss_rounds"] == 4


def test_runtime_config_preserves_distinct_saved_rounds(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_MAX_RISK_ROUNDS", raising=False)
    selections = {
        "research_depth": 2,
        "max_debate_rounds": 2,
        "max_risk_discuss_rounds": 4,
        "shallow_thinker": "gpt-5.4-mini",
        "deep_thinker": "gpt-5.5",
        "backend_url": "https://api.openai.com/v1",
        "llm_provider": "openai",
        "google_thinking_level": None,
        "openai_reasoning_effort": "high",
        "anthropic_effort": None,
        "output_language": "English",
    }

    config = m._build_run_config(selections, checkpoint=None)

    assert config["max_debate_rounds"] == 2
    assert config["max_risk_discuss_rounds"] == 4


def test_saved_preferences_are_reused_without_an_interactive_stdin(monkeypatch):
    prefs = {
        "llm_provider": "openai",
        "backend_url": "https://api.openai.com/v1",
        "quick_think_llm": "gpt-5.4-mini",
        "deep_think_llm": "gpt-5.5",
        "output_language": "English",
        "max_debate_rounds": 2,
        "max_risk_discuss_rounds": 2,
    }
    monkeypatch.setattr(m.sys, "stdin", io.StringIO())
    monkeypatch.setattr(
        m,
        "load_preferences_result",
        lambda: preferences.PreferenceLoadResult("valid", prefs),
    )
    monkeypatch.setattr(m, "display_preferences_summary", lambda _: None)

    def fail_prompt():
        raise AssertionError("unexpected interactive prompt")

    monkeypatch.setattr(
        m,
        "prompt_use_preferences",
        fail_prompt,
    )
    monkeypatch.setattr(m, "fetch_announcements", lambda: None)
    monkeypatch.setattr(m, "display_announcements", lambda *_: None)
    monkeypatch.setattr(m, "get_ticker", lambda: "AAPL")
    monkeypatch.setattr(m, "get_analysis_date", lambda: "2026-08-15")
    monkeypatch.setattr(m, "select_analysts", lambda _asset_type: [])
    monkeypatch.setattr(m, "ensure_api_key", lambda _provider: None)

    selections = m.get_user_selections()

    assert selections["llm_provider"] == "openai"
    assert selections["deep_thinker"] == "gpt-5.5"
    assert selections["research_depth"] == 2


def test_future_preferences_do_not_trigger_automatic_save(monkeypatch):
    monkeypatch.setattr(m.sys, "stdin", io.StringIO())
    monkeypatch.setattr(
        m,
        "load_preferences_result",
        lambda: preferences.PreferenceLoadResult("future"),
    )
    monkeypatch.setattr(m, "fetch_announcements", lambda: None)
    monkeypatch.setattr(m, "display_announcements", lambda *_: None)
    monkeypatch.setattr(m, "get_ticker", lambda: "AAPL")
    monkeypatch.setattr(m, "get_analysis_date", lambda: "2026-08-15")
    monkeypatch.setattr(m, "select_analysts", lambda _asset_type: [])
    monkeypatch.setattr(m, "ensure_api_key", lambda _provider: None)
    monkeypatch.setenv("TRADINGAGENTS_OUTPUT_LANGUAGE", "English")
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "2")
    monkeypatch.setenv("TRADINGAGENTS_MAX_RISK_ROUNDS", "4")
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-5.4-mini")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_THINK_LLM", "gpt-5.5")
    monkeypatch.setenv("TRADINGAGENTS_OPENAI_REASONING_EFFORT", "high")

    selections = m.get_user_selections()

    assert selections["_prefs_action"] is None


def test_first_run_does_not_prompt_to_save_in_non_tty(monkeypatch):
    selections = _valid_preferences(
        ticker="AAPL",
        asset_type="stock",
        analysis_date="2026-08-15",
        analysts=[],
        research_depth=1,
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        shallow_thinker="gpt-5.4-mini",
        deep_thinker="gpt-5.5",
        llm_provider="openai",
        _prefs_action="first_time",
    )
    monkeypatch.setattr(m, "get_user_selections", lambda configure=False: selections)
    monkeypatch.setattr(m, "_build_run_config", lambda _selections, _checkpoint: {})
    monkeypatch.setattr(m.sys, "stdin", io.StringIO())

    def fail_confirm(*_args, **_kwargs):
        raise AssertionError("non-TTY first run prompted to save preferences")

    monkeypatch.setattr(questionary, "confirm", fail_confirm)

    class _StoppedBeforeGraph(Exception):
        pass

    monkeypatch.setattr(m, "StatsCallbackHandler", lambda: object())
    monkeypatch.setattr(m, "build_analyst_execution_plan", lambda _keys: [])
    monkeypatch.setattr(m, "AnalystWallTimeTracker", lambda _plan: object())
    monkeypatch.setattr(
        m,
        "TradingAgentsGraph",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(_StoppedBeforeGraph),
    )

    with pytest.raises(_StoppedBeforeGraph):
        m.run_analysis()


def test_saved_preference_prompt_cancellation_stops_before_setup(monkeypatch):
    class _TTY:
        def isatty(self):
            return True

    monkeypatch.setattr(m.sys, "stdin", _TTY())
    monkeypatch.setattr(
        m,
        "load_preferences_result",
        lambda: preferences.PreferenceLoadResult("valid", _valid_preferences()),
    )
    monkeypatch.setattr(m, "display_preferences_summary", lambda _: None)
    monkeypatch.setattr(m, "prompt_use_preferences", lambda: None)
    monkeypatch.setattr(m, "fetch_announcements", lambda: None)
    monkeypatch.setattr(m, "display_announcements", lambda *_: None)

    def fail_setup():
        raise AssertionError("cancelled preference prompt fell through to setup")

    monkeypatch.setattr(m, "get_ticker", fail_setup)

    with pytest.raises(typer.Exit) as error:
        m.get_user_selections()

    assert error.value.exit_code == 1


def test_provider_override_drops_saved_provider_dependent_values(monkeypatch):
    prefs = {
        "llm_provider": "openai",
        "backend_url": "https://api.openai.com/v1",
        "quick_think_llm": "gpt-5.4-mini",
        "deep_think_llm": "gpt-5.5",
        "output_language": "English",
        "max_debate_rounds": 2,
        "max_risk_discuss_rounds": 4,
        "openai_reasoning_effort": "high",
    }
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "google")
    monkeypatch.delenv("TRADINGAGENTS_LLM_BACKEND_URL", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_QUICK_THINK_LLM", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_DEEP_THINK_LLM", raising=False)

    selections = preferences.preferences_to_selections(prefs, defaults=m.DEFAULT_CONFIG)

    assert selections["llm_provider"] == "google"
    assert selections["backend_url"] == provider_default_url("google")
    assert selections["shallow_thinker"] == get_model_options("google", "quick")[0][1]
    assert selections["deep_thinker"] == get_model_options("google", "deep")[0][1]
    assert selections["openai_reasoning_effort"] is None


def test_provider_override_only_applies_matching_reasoning_env(monkeypatch):
    prefs = _valid_preferences(
        openai_reasoning_effort="high",
        google_thinking_level="minimal",
    )
    defaults = dict(
        m.DEFAULT_CONFIG,
        google_thinking_level="minimal",
        openai_reasoning_effort="high",
        anthropic_effort="low",
    )
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "google")
    monkeypatch.setenv("TRADINGAGENTS_GOOGLE_THINKING_LEVEL", "minimal")
    monkeypatch.setenv("TRADINGAGENTS_OPENAI_REASONING_EFFORT", "high")
    monkeypatch.setenv("TRADINGAGENTS_ANTHROPIC_EFFORT", "low")
    for env_var in (
        "TRADINGAGENTS_LLM_BACKEND_URL",
        "TRADINGAGENTS_QUICK_THINK_LLM",
        "TRADINGAGENTS_DEEP_THINK_LLM",
    ):
        monkeypatch.delenv(env_var, raising=False)

    selections = preferences.preferences_to_selections(prefs, defaults=defaults)

    assert selections["google_thinking_level"] == "minimal"
    assert selections["openai_reasoning_effort"] is None
    assert selections["anthropic_effort"] is None


@pytest.mark.parametrize("provider", ["openai_compatible", "openrouter", "azure"])
def test_custom_only_provider_requires_matching_model_override(monkeypatch, provider):
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", provider)
    monkeypatch.delenv("TRADINGAGENTS_QUICK_THINK_LLM", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_DEEP_THINK_LLM", raising=False)

    with pytest.raises(ValueError, match="TRADINGAGENTS_QUICK_THINK_LLM"):
        preferences.preferences_to_selections(_valid_preferences())


def test_custom_only_provider_error_is_actionable_in_cli(monkeypatch, capsys):
    monkeypatch.setattr(m.sys, "stdin", io.StringIO())
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.delenv("TRADINGAGENTS_QUICK_THINK_LLM", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_DEEP_THINK_LLM", raising=False)
    monkeypatch.setattr(
        m,
        "load_preferences_result",
        lambda: preferences.PreferenceLoadResult("valid", _valid_preferences()),
    )
    monkeypatch.setattr(m, "display_preferences_summary", lambda _: None)
    monkeypatch.setattr(m, "fetch_announcements", lambda: None)
    monkeypatch.setattr(m, "display_announcements", lambda *_: None)

    with pytest.raises(typer.Exit) as error:
        m.get_user_selections()

    assert error.value.exit_code == 1
    assert "TRADINGAGENTS_QUICK_THINK_LLM" in capsys.readouterr().out
