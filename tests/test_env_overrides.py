"""Tests for TRADINGAGENTS_* env-var overlay onto DEFAULT_CONFIG."""

from __future__ import annotations

import importlib
import os

import pytest

import tradingagents.default_config as default_config_module


def _reload_with_env(monkeypatch, **overrides):
    """Set/clear env vars then reload default_config to re-evaluate DEFAULT_CONFIG."""
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    for key, val in overrides.items():
        monkeypatch.setenv(key, val)
    return importlib.reload(default_config_module)


@pytest.fixture(autouse=True)
def _restore_default_config_module(monkeypatch):
    """Reload default_config with a clean env after every test in this module.

    Reloading with overrides leaves the new values in the module-level
    DEFAULT_CONFIG; downstream consumers that lazily snapshot it (e.g.
    dataflows.config's first initialize) would otherwise observe this
    module's test values for the rest of the session.
    """
    yield
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    importlib.reload(default_config_module)


def test_no_env_uses_built_in_defaults(monkeypatch):
    dc = _reload_with_env(monkeypatch)
    assert dc.DEFAULT_CONFIG["llm_provider"] == "openai"
    assert dc.DEFAULT_CONFIG["deep_think_llm"] == "gpt-6-sol"
    assert dc.DEFAULT_CONFIG["quick_think_llm"] == "gpt-6-luna"
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


def test_empty_path_value_keeps_the_default_path(monkeypatch):
    """.env.example lists the path variables blank; uncommenting one made the
    path empty, and the graph failed creating its directories."""
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_RESULTS_DIR="",
        TRADINGAGENTS_CACHE_DIR="",
        TRADINGAGENTS_MEMORY_LOG_PATH="",
    )
    home = dc._TRADINGAGENTS_HOME
    assert dc.DEFAULT_CONFIG["results_dir"] == os.path.join(home, "logs")
    assert dc.DEFAULT_CONFIG["data_cache_dir"] == os.path.join(home, "cache")
    assert dc.DEFAULT_CONFIG["memory_log_path"] == os.path.join(home, "memory", "trading_memory.md")


def test_invalid_int_raises(monkeypatch):
    """Garbage int values should surface a ValueError at import, not silently misconfigure."""
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "not-a-number")
    with pytest.raises(ValueError, match="TRADINGAGENTS_MAX_DEBATE_ROUNDS"):
        importlib.reload(default_config_module)
    # Restore module state for subsequent tests in this process
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


# --- L2: risk guard limits and multi-exchange config -----------------------


def test_risk_and_execution_defaults(monkeypatch):
    dc = _reload_with_env(monkeypatch)
    assert dc.DEFAULT_CONFIG["risk_max_daily_loss_pct"] == 5.0
    assert dc.DEFAULT_CONFIG["risk_max_position_pct_per_asset"] == 25.0
    assert dc.DEFAULT_CONFIG["risk_max_total_exposure_pct"] == 80.0
    assert dc.DEFAULT_CONFIG["risk_max_consecutive_loss_count"] == 3
    assert isinstance(dc.DEFAULT_CONFIG["risk_max_consecutive_loss_count"], int)
    assert dc.DEFAULT_CONFIG["risk_max_derivatives_leverage"] == 1.0
    assert dc.DEFAULT_CONFIG["risk_max_derivatives_exposure_pct"] == 0.0
    assert dc.DEFAULT_CONFIG["exec_exchange_id"] == "binance"
    assert dc.DEFAULT_CONFIG["exec_symbol_overrides"] == {}
    assert dc.DEFAULT_CONFIG["exec_watchlist"] == ["BTC-USD", "ETH-USD"]
    assert dc.DEFAULT_CONFIG["exec_auto_confirm"] is False
    assert dc.DEFAULT_CONFIG["exec_derivatives"] is False


def test_risk_float_and_int_coercion(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_RISK_MAX_DAILY_LOSS_PCT="2.5",
        TRADINGAGENTS_RISK_MAX_POSITION_PCT_PER_ASSET="10",
        TRADINGAGENTS_RISK_MAX_TOTAL_EXPOSURE_PCT="60.5",
        TRADINGAGENTS_RISK_MAX_CONSECUTIVE_LOSS_COUNT="5",
        TRADINGAGENTS_RISK_MAX_DERIVATIVES_LEVERAGE="3",
        TRADINGAGENTS_RISK_MAX_DERIVATIVES_EXPOSURE_PCT="40.0",
        TRADINGAGENTS_EXEC_EXCHANGE_ID="okx",
    )
    assert dc.DEFAULT_CONFIG["risk_max_daily_loss_pct"] == 2.5
    assert isinstance(dc.DEFAULT_CONFIG["risk_max_daily_loss_pct"], float)
    assert dc.DEFAULT_CONFIG["risk_max_position_pct_per_asset"] == 10.0
    assert dc.DEFAULT_CONFIG["risk_max_total_exposure_pct"] == 60.5
    assert dc.DEFAULT_CONFIG["risk_max_consecutive_loss_count"] == 5
    assert isinstance(dc.DEFAULT_CONFIG["risk_max_consecutive_loss_count"], int)
    assert dc.DEFAULT_CONFIG["risk_max_derivatives_leverage"] == 3.0
    assert dc.DEFAULT_CONFIG["risk_max_derivatives_exposure_pct"] == 40.0
    assert dc.DEFAULT_CONFIG["exec_exchange_id"] == "okx"


@pytest.mark.parametrize(
    "env_var",
    [
        "TRADINGAGENTS_RISK_MAX_DAILY_LOSS_PCT",
        "TRADINGAGENTS_RISK_MAX_CONSECUTIVE_LOSS_COUNT",
    ],
)
def test_invalid_risk_value_raises(monkeypatch, env_var):
    """Garbage numeric risk values must fail loudly at import."""
    monkeypatch.setenv(env_var, "not-a-number")
    with pytest.raises(ValueError, match=env_var):
        importlib.reload(default_config_module)
    monkeypatch.delenv(env_var, raising=False)
    importlib.reload(default_config_module)


def test_exchange_id_accepts_any_string(monkeypatch):
    dc = _reload_with_env(monkeypatch, TRADINGAGENTS_EXEC_EXCHANGE_ID="not-a-number")
    assert dc.DEFAULT_CONFIG["exec_exchange_id"] == "not-a-number"


def test_execution_gates_and_structured_keys_are_not_env_overridable(monkeypatch):
    """exec_auto_confirm/exec_derivatives follow the exec_live pattern (fail-closed
    call-time reads, never folded into config), and _coerce cannot build the
    dict/list keys, so none of them may be env-overridable."""
    from copy import deepcopy

    monkeypatch.setenv("TRADINGAGENTS_EXEC_AUTO_CONFIRM", "true")
    monkeypatch.setenv("TRADINGAGENTS_EXEC_DERIVATIVES", "true")
    monkeypatch.setenv("TRADINGAGENTS_EXEC_WATCHLIST", "SOL-USD")
    monkeypatch.setenv("TRADINGAGENTS_EXEC_SYMBOL_OVERRIDES", "garbage")
    config = deepcopy(default_config_module.DEFAULT_CONFIG)
    default_config_module._apply_env_overrides(config)
    assert config["exec_auto_confirm"] is False
    assert config["exec_derivatives"] is False
    assert config["exec_watchlist"] == ["BTC-USD", "ETH-USD"]
    assert config["exec_symbol_overrides"] == {}
