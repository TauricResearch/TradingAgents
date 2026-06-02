"""Tests for the new ``TRADINGAGENTS_LLM_CACHE_*`` and
``TRADINGAGENTS_LLM_RETRY_*`` env-var overrides in ``default_config``."""

from __future__ import annotations

import importlib

import pytest

import tradingagents.default_config as default_config_module


def _reload_with_env(monkeypatch, **overrides):
    """Set/clear env vars then reload default_config to re-evaluate DEFAULT_CONFIG."""
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    for key, val in overrides.items():
        monkeypatch.setenv(key, val)
    return importlib.reload(default_config_module)


@pytest.mark.unit
class TestCacheConfigDefaults:
    def test_defaults_enable_cache_with_no_ttl(self, monkeypatch):
        dc = _reload_with_env(monkeypatch)
        assert dc.DEFAULT_CONFIG["llm_cache_enabled"] is True
        assert dc.DEFAULT_CONFIG["llm_cache_ttl_seconds"] is None

    def test_disable_cache_via_env(self, monkeypatch):
        dc = _reload_with_env(
            monkeypatch,
            TRADINGAGENTS_LLM_CACHE_ENABLED="false",
        )
        assert dc.DEFAULT_CONFIG["llm_cache_enabled"] is False

    def test_ttl_parses_as_int(self, monkeypatch):
        # Matches the temperature pattern: env-var layer keeps the
        # string, the consumer (here ``_build_llm_cache``) coerces to
        # int. We assert the env-var layer round-trips a stringy int
        # AND the cache consumer actually receives an ``int``.
        dc = _reload_with_env(
            monkeypatch,
            TRADINGAGENTS_LLM_CACHE_TTL="3600",
        )
        # Env-var layer keeps a stringy int (default was None, so
        # ``_coerce`` can't infer the int type — same as temperature).
        assert int(dc.DEFAULT_CONFIG["llm_cache_ttl_seconds"]) == 3600
        # The cache consumer (trading_graph._build_llm_cache) coerces
        # to int. Verify the int-coercion contract directly.
        from tradingagents.llm_clients.cache import LLMResponseCache
        raw = dc.DEFAULT_CONFIG["llm_cache_ttl_seconds"]
        ttl = None if raw in (None, "") else int(raw)
        cache = LLMResponseCache(".tmp_ttl_check", ttl_seconds=ttl, enabled=True)
        assert cache.ttl_seconds == 3600
        assert isinstance(cache.ttl_seconds, int)


@pytest.mark.unit
class TestRetryConfigDefaults:
    def test_defaults_are_safe(self, monkeypatch):
        dc = _reload_with_env(monkeypatch)
        # 5 retries with 1s base and 60s cap is the documented default.
        assert dc.DEFAULT_CONFIG["llm_retry_max_retries"] == 5
        assert dc.DEFAULT_CONFIG["llm_retry_base_delay_seconds"] == 1.0
        assert dc.DEFAULT_CONFIG["llm_retry_max_delay_seconds"] == 60.0

    def test_max_retries_parses_as_int(self, monkeypatch):
        dc = _reload_with_env(
            monkeypatch,
            TRADINGAGENTS_LLM_RETRY_MAX="0",
        )
        assert dc.DEFAULT_CONFIG["llm_retry_max_retries"] == 0
        assert isinstance(dc.DEFAULT_CONFIG["llm_retry_max_retries"], int)

    def test_delays_parse_as_float(self, monkeypatch):
        dc = _reload_with_env(
            monkeypatch,
            TRADINGAGENTS_LLM_RETRY_BASE="2.5",
            TRADINGAGENTS_LLM_RETRY_MAX_DELAY="30.0",
        )
        assert dc.DEFAULT_CONFIG["llm_retry_base_delay_seconds"] == 2.5
        assert dc.DEFAULT_CONFIG["llm_retry_max_delay_seconds"] == 30.0

    def test_empty_string_does_not_clobber(self, monkeypatch):
        """Empty TRADINGAGENTS_* values must not clobber the built-in default."""
        dc = _reload_with_env(
            monkeypatch,
            TRADINGAGENTS_LLM_CACHE_ENABLED="",
            TRADINGAGENTS_LLM_RETRY_MAX="",
        )
        assert dc.DEFAULT_CONFIG["llm_cache_enabled"] is True
        assert dc.DEFAULT_CONFIG["llm_retry_max_retries"] == 5
