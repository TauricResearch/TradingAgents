"""Configurable per-request LLM timeout.

A long high-reasoning turn on a local OpenAI-compatible thinking model (e.g.
LM Studio serving ``unsloth/qwen3.8-27b``) can exceed the openai SDK's default
per-request timeout of 600s and abort an otherwise healthy run. This adds an
opt-in ``llm_request_timeout`` knob forwarded to every provider chat client.
"""
from __future__ import annotations

import pytest

import tradingagents.default_config as default_config_module
from tradingagents.llm_clients.factory import (
    _coerce_request_timeout,
    build_llm_kwargs,
)

# --- coercion / validation -------------------------------------------------


@pytest.mark.unit
def test_coerce_accepts_positive_ints_and_numeric_strings():
    assert _coerce_request_timeout(600) == 600
    assert _coerce_request_timeout(1800) == 1800
    assert _coerce_request_timeout("1800") == 1800


@pytest.mark.unit
@pytest.mark.parametrize("bad", [0, -1, "-5"])
def test_coerce_rejects_non_positive(bad):
    with pytest.raises(ValueError, match="> 0"):
        _coerce_request_timeout(bad)


@pytest.mark.unit
@pytest.mark.parametrize("bad", [True, False])
def test_coerce_rejects_booleans(bad):
    with pytest.raises(ValueError, match="boolean"):
        _coerce_request_timeout(bad)


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["abc", "1.5", None])
def test_coerce_rejects_non_integers(bad):
    with pytest.raises(ValueError, match="integer"):
        _coerce_request_timeout(bad)


# --- forwarding into provider kwargs --------------------------------------


@pytest.mark.unit
def test_not_forwarded_when_unset_and_not_compatible():
    kwargs = build_llm_kwargs({"llm_provider": "openai", "llm_request_timeout": None})
    assert "timeout" not in kwargs


@pytest.mark.unit
def test_compatible_server_defaults_to_generous_timeout():
    # A local/openai-compatible server must always get a ceiling above the SDK's
    # 600s default so a single long high-reasoning turn doesn't abort the run.
    kwargs = build_llm_kwargs({"llm_provider": "openai_compatible", "llm_request_timeout": None})
    assert kwargs["timeout"] == 1800


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["openai_compatible", "openai", "anthropic"])
def test_explicit_value_forwarded_across_providers(provider):
    kwargs = build_llm_kwargs({"llm_provider": provider, "llm_request_timeout": 1500})
    assert kwargs["timeout"] == 1500


@pytest.mark.unit
def test_forwarded_env_string_is_coerced():
    # env vars arrive as strings; the consumer coerces (like temperature)
    kwargs = build_llm_kwargs({"llm_provider": "openai", "llm_request_timeout": "900"})
    assert kwargs["timeout"] == 900


@pytest.mark.unit
def test_invalid_config_value_fails_loudly():
    with pytest.raises(ValueError):
        build_llm_kwargs({"llm_provider": "openai", "llm_request_timeout": -1})


# --- client passthrough ----------------------------------------------------


@pytest.mark.unit
def test_openai_client_forwards_timeout_to_chat_model():
    # ChatOpenAI maps the 'timeout' alias onto its request_timeout field.
    from tradingagents.llm_clients.openai_client import OpenAIClient

    llm = OpenAIClient(
        "unsloth/qwen3.8-27b",
        base_url="http://localhost:1234/v1",
        provider="openai_compatible",
        timeout=1800,
    ).get_llm()
    assert getattr(llm, "request_timeout", None) == 1800


# --- env overlay -----------------------------------------------------------


def _config_with_env(monkeypatch, **overrides):
    """The defaults as the environment given here would set them."""
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    for key, val in overrides.items():
        monkeypatch.setenv(key, val)
    return default_config_module.build_default_config()


@pytest.mark.unit
def test_default_is_none(monkeypatch):
    config = _config_with_env(monkeypatch)
    assert config["llm_request_timeout"] is None


@pytest.mark.unit
def test_env_override_sets_config(monkeypatch):
    config = _config_with_env(monkeypatch, TRADINGAGENTS_LLM_REQUEST_TIMEOUT="1800")
    # None-default key: env value arrives as a string and is coerced downstream.
    assert config["llm_request_timeout"] == "1800"
    assert _coerce_request_timeout(config["llm_request_timeout"]) == 1800
