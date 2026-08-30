"""Configurable output-token cap (#1204).

Some model/gateway combinations (e.g. deepseek-v4-flash deployments) emit
unbounded reasoning/output and hang or trip an idle timeout. An opt-in
``max_tokens`` config knob is forwarded to every provider so a run can bound it;
Gemini names the parameter ``max_output_tokens``, so it is forwarded under the
right key per provider.
"""
from __future__ import annotations

import importlib

import pytest

import tradingagents.default_config as default_config_module
from tradingagents.graph.trading_graph import TradingAgentsGraph, _coerce_max_tokens

# --- coercion / validation -------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("value,expected", [(1, 1), (8192, 8192), ("4096", 4096)])
def test_coerce_accepts_positive_ints_and_numeric_strings(value, expected):
    assert _coerce_max_tokens(value) == expected


@pytest.mark.unit
@pytest.mark.parametrize("bad", [0, -1, "0", "-5"])
def test_coerce_rejects_non_positive(bad):
    with pytest.raises(ValueError, match="> 0"):
        _coerce_max_tokens(bad)


@pytest.mark.unit
@pytest.mark.parametrize("bad", [True, False])
def test_coerce_rejects_booleans(bad):
    with pytest.raises(ValueError, match="boolean"):
        _coerce_max_tokens(bad)


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["abc", "1.5", None])
def test_coerce_rejects_non_integers(bad):
    with pytest.raises(ValueError, match="integer"):
        _coerce_max_tokens(bad)


# --- forwarding into provider kwargs (right key per provider) --------------

def _bare_graph(config):
    g = object.__new__(TradingAgentsGraph)
    g.config = config
    return g


@pytest.mark.unit
def test_not_forwarded_when_unset():
    kwargs = _bare_graph({"llm_provider": "openai", "max_tokens": None})._get_provider_kwargs()
    assert "max_tokens" not in kwargs
    assert "max_output_tokens" not in kwargs


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["openai", "anthropic", "deepseek", "openai_compatible"])
def test_forwarded_as_max_tokens_for_non_google(provider):
    kwargs = _bare_graph({"llm_provider": provider, "max_tokens": 8192})._get_provider_kwargs()
    assert kwargs["max_tokens"] == 8192
    assert "max_output_tokens" not in kwargs


@pytest.mark.unit
def test_forwarded_as_max_output_tokens_for_google():
    # Gemini's kwarg name differs; forwarding plain max_tokens would be rejected.
    kwargs = _bare_graph({"llm_provider": "google", "max_tokens": 8192})._get_provider_kwargs()
    assert kwargs["max_output_tokens"] == 8192
    assert "max_tokens" not in kwargs


@pytest.mark.unit
def test_env_string_is_coerced():
    kwargs = _bare_graph({"llm_provider": "openai", "max_tokens": "4096"})._get_provider_kwargs()
    assert kwargs["max_tokens"] == 4096


@pytest.mark.unit
def test_invalid_value_fails_loudly():
    with pytest.raises(ValueError):
        _bare_graph({"llm_provider": "openai", "max_tokens": 0})._get_provider_kwargs()


# --- client-side allowlists carry the kwarg --------------------------------

@pytest.mark.unit
def test_openai_and_google_clients_accept_the_kwarg():
    from tradingagents.llm_clients import openai_client
    from tradingagents.llm_clients.google_client import GoogleClient  # noqa: F401
    assert "max_tokens" in openai_client._PASSTHROUGH_KWARGS
    # Google client forwards max_output_tokens through construction.
    llm = GoogleClient("gemini-3.5-flash", api_key="x", max_output_tokens=8192).get_llm()
    assert getattr(llm, "max_output_tokens", None) == 8192


# --- env overlay -----------------------------------------------------------

def _reload_with_env(monkeypatch, **overrides):
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    for key, val in overrides.items():
        monkeypatch.setenv(key, val)
    return importlib.reload(default_config_module)


@pytest.mark.unit
def test_default_is_none(monkeypatch):
    dc = _reload_with_env(monkeypatch)
    assert dc.DEFAULT_CONFIG["max_tokens"] is None


@pytest.mark.unit
def test_env_override_sets_config(monkeypatch):
    dc = _reload_with_env(monkeypatch, TRADINGAGENTS_MAX_TOKENS="8192")
    assert dc.DEFAULT_CONFIG["max_tokens"] == "8192"
    assert _coerce_max_tokens(dc.DEFAULT_CONFIG["max_tokens"]) == 8192
