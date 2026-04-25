from types import SimpleNamespace
from unittest.mock import patch

import httpx
import openai
import pytest

from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI, OpenAIClient


def _make_client(retries: int = 2) -> NormalizedChatOpenAI:
    client = object.__new__(NormalizedChatOpenAI)
    client._manual_retry_attempts = retries
    client._manual_retry_base_delay_s = 0.0
    return client


def test_invoke_retries_transient_network_disconnect():
    client = _make_client(retries=2)
    response = SimpleNamespace(content="ok")

    class FlakyInvoke:
        def __init__(self):
            self.calls = 0

        def __call__(self, _self, input, config=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise openai.APIConnectionError(request=None)
            return response

    flaky = FlakyInvoke()
    with patch("tradingagents.llm_clients.openai_client.ChatOpenAI.invoke", new=flaky):
        result = client.invoke(["hello"])

    assert result is response
    assert flaky.calls == 2


def test_invoke_does_not_retry_non_transient_api_error():
    client = _make_client(retries=2)
    error = openai.APIError("bad request", request=None, body=None)

    with patch(
        "tradingagents.llm_clients.openai_client.ChatOpenAI.invoke",
        side_effect=error,
    ) as mock_invoke:
        with pytest.raises(openai.APIError):
            client.invoke(["hello"])

    assert mock_invoke.call_count == 1


def test_invoke_retries_temporary_upstream_rate_limit():
    client = _make_client(retries=2)
    response = SimpleNamespace(content="ok")

    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    upstream_429 = httpx.Response(
        429,
        request=request,
        json={
            "error": {
                "message": "Provider returned error",
                "code": 429,
                "metadata": {
                    "raw": "qwen/qwen3.6-plus-preview:free is temporarily rate-limited upstream. Please retry shortly.",
                },
            }
        },
    )

    class FlakyInvoke:
        def __init__(self):
            self.calls = 0

        def __call__(self, _self, input, config=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise openai.RateLimitError(
                    "rate limited", response=upstream_429, body=upstream_429.json()
                )
            return response

    flaky = FlakyInvoke()
    with patch("tradingagents.llm_clients.openai_client.ChatOpenAI.invoke", new=flaky):
        result = client.invoke(["hello"])

    assert result is response
    assert flaky.calls == 2


def test_openrouter_api_key_loaded_from_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRADINGAGENTS_LOAD_DOTENV", "1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=dotenv-openrouter-key\n", encoding="utf-8")

    client = OpenAIClient(model="openrouter/test-model", provider="openrouter")

    with patch(
        "tradingagents.llm_clients.openai_client.NormalizedChatOpenAI",
        side_effect=lambda **kwargs: kwargs,
    ):
        llm_kwargs = client.get_llm()

    assert llm_kwargs["api_key"] == "dotenv-openrouter-key"
    assert llm_kwargs["base_url"] == "https://openrouter.ai/api/v1"


def test_openai_api_key_loaded_from_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRADINGAGENTS_LOAD_DOTENV", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=dotenv-openai-key\n", encoding="utf-8")

    client = OpenAIClient(model="gpt-5-mini", provider="openai")

    with patch(
        "tradingagents.llm_clients.openai_client.NormalizedChatOpenAI",
        side_effect=lambda **kwargs: kwargs,
    ):
        llm_kwargs = client.get_llm()

    assert llm_kwargs["api_key"] == "dotenv-openai-key"
    assert llm_kwargs["use_responses_api"] is True
