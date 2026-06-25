"""Tests for the configurable LLM ``max_retries`` resilience knob.

``max_retries`` is a cross-provider knob: when set it must reach the underlying
chat client so transient provider errors (HTTP 429 rate limits) are retried with
the SDK's exponential backoff; when unset the provider keeps its own default.
"""

import importlib

import pytest

from tradingagents.llm_clients.factory import create_llm_client


@pytest.mark.unit
class TestMaxRetriesForwarding:
    @pytest.mark.parametrize(
        "provider,model",
        [
            ("openai", "gpt-4.1"),
            ("anthropic", "claude-sonnet-4-6"),
            ("google", "gemini-2.5-flash"),
            ("deepseek", "deepseek-chat"),
        ],
    )
    def test_max_retries_reaches_client_when_set(self, provider, model):
        llm = create_llm_client(
            provider=provider, model=model, max_retries=8, api_key="placeholder"
        ).get_llm()
        assert llm.max_retries == 8

    def test_max_retries_reaches_azure_client(self, monkeypatch):
        # Azure's get_llm() reads its endpoint + API version from the env.
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
        monkeypatch.setenv("OPENAI_API_VERSION", "2024-10-21")
        llm = create_llm_client(
            provider="azure", model="my-deployment", max_retries=8, api_key="placeholder"
        ).get_llm()
        assert llm.max_retries == 8


@pytest.mark.unit
class TestProviderKwargsMaxRetries:
    """_get_provider_kwargs int-coerces and forwards llm_max_retries, or omits it."""

    def _kwargs_for(self, max_retries):
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        # Call the method without constructing the full graph.
        graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
        graph.config = {"llm_provider": "openai", "llm_max_retries": max_retries}
        return TradingAgentsGraph._get_provider_kwargs(graph)

    def test_int_passthrough(self):
        assert self._kwargs_for(6)["max_retries"] == 6

    def test_int_string_coerced(self):
        assert self._kwargs_for("8")["max_retries"] == 8

    def test_none_omitted(self):
        assert "max_retries" not in self._kwargs_for(None)

    def test_empty_string_omitted(self):
        assert "max_retries" not in self._kwargs_for("")

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError, match="TRADINGAGENTS_LLM_MAX_RETRIES"):
            self._kwargs_for("abc")

    def test_negative_value_raises(self):
        with pytest.raises(ValueError, match="TRADINGAGENTS_LLM_MAX_RETRIES"):
            self._kwargs_for(-1)

    def test_boolean_value_raises(self):
        # bool is an int subclass; True/False must not become 1/0 retries.
        with pytest.raises(ValueError, match="TRADINGAGENTS_LLM_MAX_RETRIES"):
            self._kwargs_for(True)
        with pytest.raises(ValueError, match="TRADINGAGENTS_LLM_MAX_RETRIES"):
            self._kwargs_for(False)


@pytest.mark.unit
class TestMaxRetriesEnvOverlay:
    """Default is None (provider keeps its own default); env var overrides it."""

    def test_default_is_none(self, monkeypatch):
        import tradingagents.default_config as dc
        monkeypatch.delenv("TRADINGAGENTS_LLM_MAX_RETRIES", raising=False)
        importlib.reload(dc)
        assert dc.DEFAULT_CONFIG["llm_max_retries"] is None

    def test_env_overrides(self, monkeypatch):
        import tradingagents.default_config as dc
        monkeypatch.setenv("TRADINGAGENTS_LLM_MAX_RETRIES", "8")
        importlib.reload(dc)
        # Stored as-is from env (string ok; consumed via int() at forward time).
        assert int(dc.DEFAULT_CONFIG["llm_max_retries"]) == 8
        monkeypatch.delenv("TRADINGAGENTS_LLM_MAX_RETRIES", raising=False)
        importlib.reload(dc)
