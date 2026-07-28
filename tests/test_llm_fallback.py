"""Optional resilience fallback (llm_fallback_provider / llm_fallback_model).

When both are set, TradingAgentsGraph wraps the deep- and quick-thinking LLMs
with LangChain's native `.with_fallbacks`, so a run survives the primary
provider being down, rate-limited, or deprecated (e.g. a free OpenRouter model
that gets pulled) instead of aborting. Unset (the default) is a strict no-op.
"""
from __future__ import annotations

import importlib

import pytest

import tradingagents.default_config as default_config_module
from tradingagents.graph.trading_graph import _apply_llm_fallback


class _FakeLLM:
    """Minimal stand-in for a LangChain chat model's `.with_fallbacks` surface."""

    def __init__(self, name):
        self.name = name
        self.fallback_calls: list = []

    def with_fallbacks(self, fallbacks):
        self.fallback_calls.append(fallbacks)
        wrapped = _FakeLLM(f"{self.name}+fallback")
        wrapped.fallbacks = fallbacks
        return wrapped


# --- _apply_llm_fallback: no-op cases ---------------------------------------

@pytest.mark.unit
def test_noop_when_both_unset():
    deep, quick = _FakeLLM("deep"), _FakeLLM("quick")
    out_deep, out_quick = _apply_llm_fallback({}, deep, quick)
    assert out_deep is deep
    assert out_quick is quick
    assert deep.fallback_calls == []
    assert quick.fallback_calls == []


@pytest.mark.unit
def test_noop_when_only_provider_set():
    deep, quick = _FakeLLM("deep"), _FakeLLM("quick")
    out_deep, out_quick = _apply_llm_fallback({"llm_fallback_provider": "ollama"}, deep, quick)
    assert out_deep is deep
    assert out_quick is quick


@pytest.mark.unit
def test_noop_when_only_model_set():
    deep, quick = _FakeLLM("deep"), _FakeLLM("quick")
    out_deep, out_quick = _apply_llm_fallback({"llm_fallback_model": "lfm2.5:8b"}, deep, quick)
    assert out_deep is deep
    assert out_quick is quick


# --- _apply_llm_fallback: active case (real create_llm_client, no network) --

@pytest.mark.unit
def test_applies_fallback_to_both_tiers_when_configured():
    deep, quick = _FakeLLM("deep"), _FakeLLM("quick")
    config = {"llm_fallback_provider": "ollama", "llm_fallback_model": "lfm2.5:8b"}
    out_deep, out_quick = _apply_llm_fallback(config, deep, quick)
    assert out_deep is not deep
    assert out_quick is not quick
    assert len(deep.fallback_calls) == 1
    assert len(quick.fallback_calls) == 1


@pytest.mark.unit
def test_both_tiers_share_one_fallback_client():
    """A resilience net doesn't need its own quick/deep quality split."""
    deep, quick = _FakeLLM("deep"), _FakeLLM("quick")
    config = {"llm_fallback_provider": "ollama", "llm_fallback_model": "lfm2.5:8b"}
    _apply_llm_fallback(config, deep, quick)
    assert deep.fallback_calls[0] == quick.fallback_calls[0]


# --- temperature forwarding --------------------------------------------------

@pytest.mark.unit
def test_temperature_forwarded_to_fallback_client(monkeypatch):
    captured = {}

    def fake_create_llm_client(provider, model, **kwargs):
        captured.update(kwargs)

        class _Client:
            def get_llm(self):
                return _FakeLLM("fallback")

        return _Client()

    import tradingagents.graph.trading_graph as tg
    monkeypatch.setattr(tg, "create_llm_client", fake_create_llm_client)

    config = {
        "llm_fallback_provider": "ollama",
        "llm_fallback_model": "lfm2.5:8b",
        "temperature": "0.2",  # env vars arrive as strings, like elsewhere in this module
    }
    tg._apply_llm_fallback(config, _FakeLLM("deep"), _FakeLLM("quick"))
    assert captured["temperature"] == 0.2
    assert isinstance(captured["temperature"], float)


@pytest.mark.unit
def test_temperature_not_forwarded_when_unset(monkeypatch):
    captured = {}

    def fake_create_llm_client(provider, model, **kwargs):
        captured.update(kwargs)

        class _Client:
            def get_llm(self):
                return _FakeLLM("fallback")

        return _Client()

    import tradingagents.graph.trading_graph as tg
    monkeypatch.setattr(tg, "create_llm_client", fake_create_llm_client)

    config = {"llm_fallback_provider": "ollama", "llm_fallback_model": "lfm2.5:8b"}
    tg._apply_llm_fallback(config, _FakeLLM("deep"), _FakeLLM("quick"))
    assert "temperature" not in captured


# --- env overlay -------------------------------------------------------------

def _reload_with_env(monkeypatch, **overrides):
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    for key, val in overrides.items():
        monkeypatch.setenv(key, val)
    return importlib.reload(default_config_module)


@pytest.mark.unit
def test_fallback_config_defaults_to_none(monkeypatch):
    dc = _reload_with_env(monkeypatch)
    assert dc.DEFAULT_CONFIG["llm_fallback_provider"] is None
    assert dc.DEFAULT_CONFIG["llm_fallback_model"] is None


@pytest.mark.unit
def test_fallback_env_overrides_set_config(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_LLM_FALLBACK_PROVIDER="ollama",
        TRADINGAGENTS_LLM_FALLBACK_MODEL="lfm2.5:8b",
    )
    assert dc.DEFAULT_CONFIG["llm_fallback_provider"] == "ollama"
    assert dc.DEFAULT_CONFIG["llm_fallback_model"] == "lfm2.5:8b"
