"""Tests for TRADINGAGENTS_* env-var overlay onto DEFAULT_CONFIG."""

from __future__ import annotations

import importlib
import os
import stat
import subprocess
import sys
import traceback

import pytest

import tradingagents.default_config as default_config_module


def _clean_subprocess_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key not in default_config_module._ENV_OVERRIDES
    }


@pytest.mark.unit
def test_package_import_does_not_load_project_environment(tmp_path):
    (tmp_path / ".env").write_text("TRADINGAGENTS_LLM_PROVIDER=google\n")

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, tradingagents; print(os.getenv('TRADINGAGENTS_LLM_PROVIDER', 'unset'))",
        ],
        cwd=tmp_path,
        env=_clean_subprocess_env(),
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip() == "unset"


@pytest.mark.unit
def test_default_config_never_searches_parent_directories_for_env(tmp_path):
    (tmp_path / ".env").write_text("TRADINGAGENTS_LLM_PROVIDER=untrusted-parent\n")
    child = tmp_path / "child"
    child.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from tradingagents.default_config import DEFAULT_CONFIG; "
            "print(DEFAULT_CONFIG['llm_provider'])",
        ],
        cwd=child,
        env=_clean_subprocess_env(),
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip() == "openai"


@pytest.mark.unit
def test_application_entrypoint_loads_only_the_current_project_env(tmp_path):
    (tmp_path / ".env").write_text("TRADINGAGENTS_LLM_PROVIDER=google\n")

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; from cli.entrypoints import _load_project_environment; "
            "_load_project_environment(); print(os.environ['TRADINGAGENTS_LLM_PROVIDER'])",
        ],
        cwd=tmp_path,
        env=_clean_subprocess_env(),
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip() == "google"
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600


def _reload_with_env(monkeypatch, **overrides):
    """Set/clear env vars then reload default_config to re-evaluate DEFAULT_CONFIG."""
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    for key, val in overrides.items():
        monkeypatch.setenv(key, val)
    return importlib.reload(default_config_module)


def test_no_env_uses_built_in_defaults(monkeypatch):
    dc = _reload_with_env(monkeypatch)
    assert dc.DEFAULT_CONFIG["llm_provider"] == "openai"
    assert dc.DEFAULT_CONFIG["deep_think_llm"] == "gpt-5.5"
    assert dc.DEFAULT_CONFIG["quick_think_llm"] == "gpt-5.4-mini"
    assert dc.DEFAULT_CONFIG["backend_url"] is None
    assert dc.DEFAULT_CONFIG["max_debate_rounds"] == 1
    assert dc.DEFAULT_CONFIG["checkpoint_enabled"] is False


def test_string_overrides(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_LLM_PROVIDER="google",
        TRADINGAGENTS_DEEP_THINK_LLM="gemini-3-pro-preview",
        TRADINGAGENTS_QUICK_THINK_LLM="gemini-3-flash-preview",
        TRADINGAGENTS_LLM_BACKEND_URL="https://example.invalid/v1",
        TRADINGAGENTS_OUTPUT_LANGUAGE="Chinese",
    )
    assert dc.DEFAULT_CONFIG["llm_provider"] == "google"
    assert dc.DEFAULT_CONFIG["deep_think_llm"] == "gemini-3-pro-preview"
    assert dc.DEFAULT_CONFIG["quick_think_llm"] == "gemini-3-flash-preview"
    assert dc.DEFAULT_CONFIG["backend_url"] == "https://example.invalid/v1"
    assert dc.DEFAULT_CONFIG["output_language"] == "Chinese"


def test_int_coercion(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_MAX_DEBATE_ROUNDS="3",
        TRADINGAGENTS_MAX_RISK_ROUNDS="2",
    )
    assert dc.DEFAULT_CONFIG["max_debate_rounds"] == 3
    assert isinstance(dc.DEFAULT_CONFIG["max_debate_rounds"], int)
    assert dc.DEFAULT_CONFIG["max_risk_discuss_rounds"] == 2
    assert isinstance(dc.DEFAULT_CONFIG["max_risk_discuss_rounds"], int)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
        ("false", False), ("False", False), ("0", False), ("no", False), ("off", False),
    ],
)
def test_bool_coercion(monkeypatch, raw, expected):
    dc = _reload_with_env(monkeypatch, TRADINGAGENTS_CHECKPOINT_ENABLED=raw)
    assert dc.DEFAULT_CONFIG["checkpoint_enabled"] is expected


def test_reasoning_thinking_overrides(monkeypatch):
    """The provider reasoning/thinking knobs are env-configurable (non-interactive runs)."""
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_OPENAI_REASONING_EFFORT="high",
        TRADINGAGENTS_GOOGLE_THINKING_LEVEL="minimal",
        TRADINGAGENTS_ANTHROPIC_EFFORT="low",
    )
    assert dc.DEFAULT_CONFIG["openai_reasoning_effort"] == "high"
    assert dc.DEFAULT_CONFIG["google_thinking_level"] == "minimal"
    assert dc.DEFAULT_CONFIG["anthropic_effort"] == "low"


def test_reasoning_effort_defaults_to_none(monkeypatch):
    """Unset reasoning/thinking knobs stay None so each provider uses its own default."""
    dc = _reload_with_env(monkeypatch)
    assert dc.DEFAULT_CONFIG["openai_reasoning_effort"] is None
    assert dc.DEFAULT_CONFIG["google_thinking_level"] is None
    assert dc.DEFAULT_CONFIG["anthropic_effort"] is None


def test_empty_env_value_is_passthrough(monkeypatch):
    """Empty TRADINGAGENTS_* values must not clobber the built-in default."""
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_LLM_PROVIDER="",
        TRADINGAGENTS_MAX_DEBATE_ROUNDS="",
    )
    assert dc.DEFAULT_CONFIG["llm_provider"] == "openai"
    assert dc.DEFAULT_CONFIG["max_debate_rounds"] == 1


def test_invalid_int_raises(monkeypatch):
    """Garbage int values should surface a ValueError at import, not silently misconfigure."""
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "not-a-number")
    with pytest.raises(ValueError, match="TRADINGAGENTS_MAX_DEBATE_ROUNDS"):
        importlib.reload(default_config_module)
    # Restore module state for subsequent tests in this process
    monkeypatch.delenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", raising=False)
    importlib.reload(default_config_module)


def test_invalid_env_value_is_not_rendered(monkeypatch):
    secret = "https://config.invalid/?token=must-not-escape"
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", secret)
    with pytest.raises(ValueError) as captured:
        importlib.reload(default_config_module)

    rendered = "".join(traceback.format_exception(captured.value))
    assert "TRADINGAGENTS_MAX_DEBATE_ROUNDS" in rendered
    assert "expected an integer" in rendered
    assert secret not in rendered

    monkeypatch.delenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", raising=False)
    importlib.reload(default_config_module)


@pytest.mark.parametrize("bad", ["treu", "flase", "maybe", "2", "enabled"])
def test_invalid_bool_raises(monkeypatch, bad):
    """A misspelled boolean must fail loudly (like ints) instead of silently False."""
    monkeypatch.setenv("TRADINGAGENTS_CHECKPOINT_ENABLED", bad)
    with pytest.raises(ValueError, match="TRADINGAGENTS_CHECKPOINT_ENABLED"):
        importlib.reload(default_config_module)
    monkeypatch.delenv("TRADINGAGENTS_CHECKPOINT_ENABLED", raising=False)
    importlib.reload(default_config_module)


def test_unknown_env_var_is_ignored(monkeypatch):
    """Env vars outside _ENV_OVERRIDES must not bleed into DEFAULT_CONFIG."""
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_NONEXISTENT_KEY="oops",
    )
    assert "nonexistent_key" not in dc.DEFAULT_CONFIG
