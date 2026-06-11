"""Tests for proactive LLM request pacing (``llm_requests_per_minute``).

The limiter is built once in ``TradingAgentsGraph`` and shared by the deep
and quick clients (a per-process total), then forwarded to the chat-model
constructor through each provider client's passthrough kwargs.
"""

from types import SimpleNamespace

import pytest
from langchain_core.rate_limiters import InMemoryRateLimiter

from tradingagents.graph.trading_graph import TradingAgentsGraph, _build_rate_limiter
from tradingagents.llm_clients import (
    anthropic_client,
    azure_client,
    google_client,
    openai_client,
)


@pytest.mark.unit
class TestBuildRateLimiter:
    @pytest.mark.parametrize("rpm", [None, "", 0, "0", -5, "-5"])
    def test_unset_or_nonpositive_disables(self, rpm):
        assert _build_rate_limiter(rpm) is None

    @pytest.mark.parametrize("rpm", [30, 30.0, "30"])
    def test_rpm_converts_to_requests_per_second(self, rpm):
        limiter = _build_rate_limiter(rpm)
        assert isinstance(limiter, InMemoryRateLimiter)
        assert limiter.requests_per_second == pytest.approx(0.5)

    def test_bucket_never_below_one_request(self):
        # rps < 1 with a same-sized bucket would never accumulate a full
        # token, deadlocking every call.
        assert _build_rate_limiter(6).max_bucket_size == 1.0


@pytest.mark.unit
class TestProviderKwargs:
    def _kwargs_for(self, config):
        # _get_provider_kwargs only touches self.config — no graph construction.
        return TradingAgentsGraph._get_provider_kwargs(SimpleNamespace(config=config))

    def test_rpm_config_yields_shared_limiter(self):
        kwargs = self._kwargs_for({"llm_provider": "anthropic", "llm_requests_per_minute": 30})
        assert isinstance(kwargs["rate_limiter"], InMemoryRateLimiter)

    def test_unset_rpm_omits_limiter(self):
        kwargs = self._kwargs_for({"llm_provider": "anthropic"})
        assert "rate_limiter" not in kwargs


@pytest.mark.unit
class TestPassthrough:
    def test_anthropic_forwards_rate_limiter(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            anthropic_client, "NormalizedChatAnthropic",
            lambda **kwargs: captured.setdefault("kwargs", kwargs),
        )
        limiter = _build_rate_limiter(30)
        anthropic_client.AnthropicClient(
            model="claude-haiku-4-5", api_key="x", rate_limiter=limiter
        ).get_llm()
        assert captured["kwargs"]["rate_limiter"] is limiter

    def test_openai_forwards_rate_limiter(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            openai_client, "NormalizedChatOpenAI",
            lambda **kwargs: captured.setdefault("kwargs", kwargs),
        )
        limiter = _build_rate_limiter(30)
        openai_client.OpenAIClient(
            model="gpt-5.4-mini", provider="openai", rate_limiter=limiter
        ).get_llm()
        assert captured["kwargs"]["rate_limiter"] is limiter

    def test_google_forwards_rate_limiter(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            google_client, "NormalizedChatGoogleGenerativeAI",
            lambda **kwargs: captured.setdefault("kwargs", kwargs),
        )
        limiter = _build_rate_limiter(30)
        google_client.GoogleClient(
            model="gemini-3-flash-preview", api_key="x", rate_limiter=limiter
        ).get_llm()
        assert captured["kwargs"]["rate_limiter"] is limiter

    def test_azure_forwards_rate_limiter(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            azure_client, "NormalizedAzureChatOpenAI",
            lambda **kwargs: captured.setdefault("kwargs", kwargs),
        )
        limiter = _build_rate_limiter(30)
        azure_client.AzureOpenAIClient(
            model="gpt-5.5", api_key="x", rate_limiter=limiter
        ).get_llm()
        assert captured["kwargs"]["rate_limiter"] is limiter
