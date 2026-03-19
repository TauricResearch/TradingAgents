"""Tests that TRADINGAGENTS_* environment variables override DEFAULT_CONFIG."""

import importlib
import os
from unittest.mock import patch

import pytest


class TestEnvOverridesDefaults:
    """Verify that setting TRADINGAGENTS_<KEY> env vars changes DEFAULT_CONFIG."""

    def _reload_config(self):
        """Force-reimport default_config so the module-level dict is rebuilt."""
        import tradingagents.default_config as mod

        importlib.reload(mod)
        return mod.DEFAULT_CONFIG

    def test_llm_provider_override(self):
        with patch.dict(os.environ, {"TRADINGAGENTS_LLM_PROVIDER": "openrouter"}):
            cfg = self._reload_config()
            assert cfg["llm_provider"] == "openrouter"

    def test_backend_url_override(self):
        with patch.dict(os.environ, {"TRADINGAGENTS_BACKEND_URL": "http://localhost:1234"}):
            cfg = self._reload_config()
            assert cfg["backend_url"] == "http://localhost:1234"

    def test_deep_think_llm_override(self):
        with patch.dict(os.environ, {"TRADINGAGENTS_DEEP_THINK_LLM": "deepseek/deepseek-r1"}):
            cfg = self._reload_config()
            assert cfg["deep_think_llm"] == "deepseek/deepseek-r1"

    def test_quick_think_llm_override(self):
        with patch.dict(os.environ, {"TRADINGAGENTS_QUICK_THINK_LLM": "gpt-4o-mini"}):
            cfg = self._reload_config()
            assert cfg["quick_think_llm"] == "gpt-4o-mini"

    def test_mid_think_llm_none_by_default(self):
        """mid_think_llm defaults to None (falls back to quick_think_llm).

        Root cause of previous failure: importlib.reload() re-runs load_dotenv(),
        which reads TRADINGAGENTS_MID_THINK_LLM from the user's .env file even
        after we pop it from os.environ.  Fix: clear all TRADINGAGENTS_* vars AND
        patch load_dotenv so it can't re-inject them from the .env file.
        """
        env_clean = {k: v for k, v in os.environ.items() if not k.startswith("TRADINGAGENTS_")}
        with patch.dict(os.environ, env_clean, clear=True):
            with patch("dotenv.load_dotenv"):
                cfg = self._reload_config()
                assert cfg["mid_think_llm"] is None

    def test_mid_think_llm_override(self):
        with patch.dict(os.environ, {"TRADINGAGENTS_MID_THINK_LLM": "gpt-4o"}):
            cfg = self._reload_config()
            assert cfg["mid_think_llm"] == "gpt-4o"

    def test_empty_env_var_keeps_default(self):
        """An empty string is treated the same as unset (keeps the default)."""
        with patch.dict(os.environ, {"TRADINGAGENTS_LLM_PROVIDER": ""}):
            cfg = self._reload_config()
            assert cfg["llm_provider"] == "openai"

    def test_empty_env_var_keeps_none_default(self):
        """An empty string for a None-default field stays None."""
        with patch.dict(os.environ, {"TRADINGAGENTS_DEEP_THINK_LLM_PROVIDER": ""}):
            cfg = self._reload_config()
            assert cfg["deep_think_llm_provider"] is None

    def test_per_tier_provider_override(self):
        with patch.dict(os.environ, {"TRADINGAGENTS_DEEP_THINK_LLM_PROVIDER": "anthropic"}):
            cfg = self._reload_config()
            assert cfg["deep_think_llm_provider"] == "anthropic"

    def test_per_tier_backend_url_override(self):
        with patch.dict(os.environ, {"TRADINGAGENTS_MID_THINK_BACKEND_URL": "http://my-ollama:11434"}):
            cfg = self._reload_config()
            assert cfg["mid_think_backend_url"] == "http://my-ollama:11434"

    def test_max_debate_rounds_int(self):
        with patch.dict(os.environ, {"TRADINGAGENTS_MAX_DEBATE_ROUNDS": "3"}):
            cfg = self._reload_config()
            assert cfg["max_debate_rounds"] == 3

    def test_max_debate_rounds_bad_value(self):
        """Non-numeric string falls back to hardcoded default."""
        with patch.dict(os.environ, {"TRADINGAGENTS_MAX_DEBATE_ROUNDS": "abc"}):
            cfg = self._reload_config()
            assert cfg["max_debate_rounds"] == 2

    def test_results_dir_override(self):
        with patch.dict(os.environ, {"TRADINGAGENTS_RESULTS_DIR": "/tmp/my_results"}):
            cfg = self._reload_config()
            assert cfg["results_dir"] == "/tmp/my_results"

    def test_vendor_scanner_data_override(self):
        with patch.dict(os.environ, {"TRADINGAGENTS_VENDOR_SCANNER_DATA": "alpha_vantage"}):
            cfg = self._reload_config()
            assert cfg["data_vendors"]["scanner_data"] == "alpha_vantage"

    def test_defaults_unchanged_when_no_env_set(self):
        """Without any TRADINGAGENTS_* vars, defaults are the original hardcoded values.

        Root cause of previous failure: importlib.reload() re-runs load_dotenv(),
        which reads TRADINGAGENTS_DEEP_THINK_LLM etc. from the user's .env file
        even though we strip them from os.environ with clear=True.  Fix: also
        patch load_dotenv to prevent the .env file from being re-read.
        """
        env_clean = {k: v for k, v in os.environ.items() if not k.startswith("TRADINGAGENTS_")}
        with patch.dict(os.environ, env_clean, clear=True):
            with patch("dotenv.load_dotenv"):
                cfg = self._reload_config()
                assert cfg["llm_provider"] == "openai"
                assert cfg["deep_think_llm"] == "gpt-5.2"
                assert cfg["mid_think_llm"] is None
                assert cfg["quick_think_llm"] == "gpt-5-mini"
                assert cfg["backend_url"] == "https://api.openai.com/v1"
                assert cfg["max_debate_rounds"] == 2
                assert cfg["data_vendors"]["scanner_data"] == "yfinance"
