from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _load_run_node_live_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "run_node_live.py"
    spec = importlib.util.spec_from_file_location("run_node_live_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("raw_timeout", ["0", "-1", "inf", "nan"])
def test_run_node_live_request_timeout_rejects_invalid_values(monkeypatch, raw_timeout):
    module = _load_run_node_live_module()

    monkeypatch.setenv("TRADINGAGENTS_RUN_NODE_LIVE_REQUEST_TIMEOUT_SEC", raw_timeout)

    assert module._request_timeout() == 30.0


@pytest.mark.parametrize("raw_timeout", ["0", "-1", "inf", "nan"])
def test_ollama_tags_timeout_rejects_invalid_values(monkeypatch, raw_timeout):
    from cli import utils

    captured = {}
    response = MagicMock()
    response.json.return_value = {"models": [{"name": "qwen2.5:7b"}]}

    def _get(_url, *, timeout):
        captured["timeout"] = timeout
        return response

    monkeypatch.setenv("TRADINGAGENTS_OLLAMA_TAGS_TIMEOUT_SEC", raw_timeout)
    with patch("cli.utils.requests.get", _get):
        assert utils._fetch_ollama_models() == [("qwen2.5:7b", "qwen2.5:7b")]

    assert captured["timeout"] == 5.0


# ---------------------------------------------------------------------------
# _env_timeout_seconds in default_config
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_value,expected",
    [
        ("30", 30.0),
        ("120.5", 120.5),
        ("0", 60.0),  # zero → fallback
        ("-1", 60.0),  # negative → fallback
        ("inf", 60.0),  # non-finite → fallback
        ("nan", 60.0),  # non-finite → fallback
        ("not_a_number", 60.0),  # parse error → fallback
    ],
)
def test_env_timeout_seconds_validates_and_falls_back(raw_value, expected, monkeypatch):
    from tradingagents import default_config

    env = {"TRADINGAGENTS_TEST_TIMEOUT_SEC": raw_value}
    result = default_config._env_timeout_seconds("TEST_TIMEOUT_SEC", 60.0, env=env)
    assert result == expected
    assert math.isfinite(result)
    assert result > 0


def test_env_timeout_seconds_uses_default_when_key_missing():
    from tradingagents import default_config

    result = default_config._env_timeout_seconds("MISSING_KEY_XYZ", 42.0, env={})
    assert result == 42.0


# ---------------------------------------------------------------------------
# Default config timeout keys must be finite and positive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config_key,default_value",
    [
        ("llm_timeout", 300.0),
        ("tool_loop_timeout_cap", 300.0),
        ("scanner_summarizer_timeout", 180.0),
        ("tool_execution_timeout", 60.0),
        ("scan_timeout_seconds", 1800.0),
        ("deep_think_llm_timeout_cap", 360.0),
        ("mid_think_llm_timeout_cap", 240.0),
        ("quick_think_llm_timeout_cap", 300.0),
    ],
)
def test_default_config_timeout_keys_are_finite_positive(config_key, default_value):
    from tradingagents.default_config import build_default_config

    # Explicitly pass empty environ to ensure we are testing hardcoded
    # defaults even if process environment has overrides.
    cfg = build_default_config(load_dotenv=False, environ={})
    val = cfg.get(config_key)

    assert val is not None, f"{config_key} must be present in DEFAULT_CONFIG"
    assert isinstance(val, float)
    assert math.isfinite(val), f"{config_key}={val} must be finite"
    assert val > 0, f"{config_key}={val} must be > 0"
    assert val == default_value


def test_optional_per_tier_timeout_is_none_when_not_configured():
    """Optional per-tier timeout overrides must be None when not set in env."""
    from tradingagents.default_config import build_default_config

    cfg = build_default_config(load_dotenv=False, environ={})
    # When the env var is absent, the value must be None (not a fallback float),
    # so the caller's 'is None' fallback chain can take effect.
    for key in ["deep_think_llm_timeout", "mid_think_llm_timeout", "quick_think_llm_timeout"]:
        assert cfg.get(key) is None, f"{key} must be None when env var is absent"


@pytest.mark.parametrize(
    "env_key,config_key",
    [
        ("TRADINGAGENTS_LLM_TIMEOUT_SEC", "llm_timeout"),
        ("TRADINGAGENTS_SCANNER_SUMMARIZER_TIMEOUT_SEC", "scanner_summarizer_timeout"),
        ("TRADINGAGENTS_TOOL_EXECUTION_TIMEOUT_SEC", "tool_execution_timeout"),
    ],
)
@pytest.mark.parametrize("bad_value", ["0", "-5", "inf", "nan"])
def test_default_config_rejects_invalid_timeout_env(env_key, config_key, bad_value, monkeypatch):
    """Invalid env values for timeout keys must fall back to the hardcoded default."""
    from tradingagents.default_config import build_default_config

    monkeypatch.setenv(env_key, bad_value)
    cfg = build_default_config(load_dotenv=False)
    val = cfg.get(config_key)
    assert math.isfinite(val), f"{config_key} must remain finite when env={bad_value!r}"
    assert val > 0, f"{config_key} must remain positive when env={bad_value!r}"


# ---------------------------------------------------------------------------
# _rate_limited_request uses env-based default when no timeout is supplied
# ---------------------------------------------------------------------------


def test_finnhub_rate_limited_request_uses_env_timeout(monkeypatch):
    """_rate_limited_request passes None to _make_api_request so the env default is applied."""
    from tradingagents.dataflows import finnhub_common

    monkeypatch.setenv("FINNHUB_API_KEY", "test_key")

    captured = {}

    def _fake_make_request(endpoint, params, timeout=None):
        captured["timeout"] = timeout
        return {}

    monkeypatch.setattr(finnhub_common, "_make_api_request", _fake_make_request)

    finnhub_common._rate_limited_request("quote", {"symbol": "AAPL"})
    # _rate_limited_request must not inject a hardcoded timeout; it passes
    # None so _make_api_request can apply _default_timeout() from the env.
    assert captured["timeout"] is None


def test_alpha_vantage_rate_limited_request_uses_env_timeout(monkeypatch):
    """_rate_limited_request passes None to _make_api_request so the env default is applied."""
    from tradingagents.dataflows import alpha_vantage_common

    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test_key")

    captured = {}

    def _fake_make_request(function_name, params, timeout=None):
        captured["timeout"] = timeout
        return {}

    monkeypatch.setattr(alpha_vantage_common, "_make_api_request", _fake_make_request)

    alpha_vantage_common._rate_limited_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
    # _rate_limited_request must not inject a hardcoded timeout; it passes
    # None so _make_api_request can apply _default_timeout() from the env.
    assert captured["timeout"] is None
