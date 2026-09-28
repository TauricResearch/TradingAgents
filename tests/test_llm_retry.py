"""Every agent retries a model that is temporarily unavailable.

The retry sits on the chat client's invoke, which is the one call every
agent makes: analysts, researchers, the trader, the portfolio manager, and
the post-run reflection. A Gemini 503 ("high demand") is the case that
used to abort Market Analyst after the provider SDK's short retry budget.
"""

from __future__ import annotations

import inspect

import pytest
from langchain_google_genai.chat_models import GoogleAPIError

from tradingagents.llm_clients.anthropic_client import NormalizedChatAnthropic
from tradingagents.llm_clients.azure_client import NormalizedAzureChatOpenAI
from tradingagents.llm_clients.google_client import NormalizedChatGoogleGenerativeAI
from tradingagents.llm_clients.openai_client import (
    DeepSeekChatOpenAI,
    LocalCompatibleChatOpenAI,
    MinimaxChatOpenAI,
    NormalizedChatOpenAI,
)
from tradingagents.llm_clients.retry import (
    _wait_seconds,
    call_with_retry,
    invoke_with_retry,
    is_transient_llm_error,
    sdk_max_retries,
)

# The payload Gemini returns when the model is overloaded.
_HIGH_DEMAND = {
    "error": {
        "code": 503,
        "message": (
            "This model is currently experiencing high demand. "
            "Spikes in demand are usually temporary. Please try again later."
        ),
        "status": "UNAVAILABLE",
    }
}

_CHAT_MODELS = (
    NormalizedChatOpenAI,
    LocalCompatibleChatOpenAI,
    DeepSeekChatOpenAI,
    MinimaxChatOpenAI,
    NormalizedChatGoogleGenerativeAI,
    NormalizedChatAnthropic,
    NormalizedAzureChatOpenAI,
)


def _unavailable() -> GoogleAPIError:
    return GoogleAPIError(503, _HIGH_DEMAND)


def _patch_sleep(monkeypatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(
        "tradingagents.llm_clients.retry.time.sleep", lambda seconds: slept.append(seconds)
    )
    # Upper bound of the jitter range: equal jitter then waits the full backoff.
    monkeypatch.setattr("tradingagents.llm_clients.retry.random.uniform", lambda _a, b: b)
    return slept


class _Parent:
    def __init__(self):
        self.calls = 0

    def invoke(self, input, config=None, **kwargs):
        self.calls += 1
        if self.calls < 3:
            raise _unavailable()
        return type("Response", (), {"content": "ok"})()


class _Model(_Parent):
    """Same shape as the provider clients: super().invoke, then the shared retry."""

    def invoke(self, input, config=None, **kwargs):
        return invoke_with_retry(super().invoke, input, config, kwargs)


@pytest.mark.unit
def test_gemini_high_demand_503_is_transient():
    err = _unavailable()
    assert "503 UNAVAILABLE" in str(err)
    assert is_transient_llm_error(err)


@pytest.mark.unit
@pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504, 529])
def test_overloaded_status_codes_are_transient(code):
    class _HTTP(Exception):
        def __init__(self):
            super().__init__(f"HTTP {code}")
            self.status_code = code

    assert is_transient_llm_error(_HTTP())


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc",
    [
        ValueError("bad request"),
        RuntimeError("provider unavailable"),
        type("Client", (Exception,), {"status_code": 400})("rejected"),
        type("Auth", (Exception,), {"is_retryable": False})("no"),
    ],
)
def test_permanent_errors_are_not_retried(exc):
    assert not is_transient_llm_error(exc)


@pytest.mark.unit
def test_a_wrapped_503_is_transient():
    try:
        raise _unavailable()
    except GoogleAPIError as err:
        wrapped = RuntimeError("node failed")
        wrapped.__cause__ = err
    assert is_transient_llm_error(wrapped)


@pytest.mark.unit
def test_connection_failures_are_transient():
    assert is_transient_llm_error(ConnectionError("reset"))
    assert is_transient_llm_error(TimeoutError("timed out"))
    assert is_transient_llm_error(type("ReadTimeout", (Exception,), {})("slow"))


@pytest.mark.unit
def test_invoke_retries_a_503_then_returns(monkeypatch):
    slept = _patch_sleep(monkeypatch)
    model = _Model()

    assert model.invoke("prompt").content == "ok"
    assert model.calls == 3
    assert slept == [20.0, 40.0]


@pytest.mark.unit
def test_invoke_stops_after_the_retry_budget(monkeypatch):
    slept = _patch_sleep(monkeypatch)

    def boom():
        raise _unavailable()

    with pytest.raises(GoogleAPIError, match="503"):
        call_with_retry(boom)
    # Four attempts: the original call plus waits of 20s, 40s and 80s.
    assert slept == [20.0, 40.0, 80.0]


@pytest.mark.unit
def test_a_permanent_error_is_not_retried(monkeypatch):
    slept = _patch_sleep(monkeypatch)
    calls = {"n": 0}

    def bad():
        calls["n"] += 1
        raise ValueError("bad tool arguments")

    with pytest.raises(ValueError, match="bad tool arguments"):
        call_with_retry(bad)
    assert calls["n"] == 1
    assert slept == []


@pytest.mark.unit
@pytest.mark.parametrize("model_cls", _CHAT_MODELS, ids=lambda cls: cls.__name__)
def test_every_provider_chat_model_retries(model_cls):
    # Inherited invoke (DeepSeek, MiniMax, local servers) counts: they use
    # NormalizedChatOpenAI.invoke, which is the shared retry.
    assert "invoke_with_retry" in inspect.getsource(model_cls.invoke)


class _Response:
    def __init__(self, status, headers=None, body=None):
        self.status_code = status
        self.headers = headers or {}
        self.body = body


class _Status(Exception):
    def __init__(self, status, headers=None, body=None, code=None):
        super().__init__(f"HTTP {status}")
        self.status_code = status
        self.response = _Response(status, headers, body)
        self.body = body
        self.code = code


@pytest.mark.unit
def test_openai_rate_limit_and_anthropic_overload_are_transient():
    # OpenAI puts a string in ``code`` and the HTTP status in ``status_code``.
    assert is_transient_llm_error(_Status(429, code="rate_limit_exceeded"))
    assert is_transient_llm_error(_Status(529))
    assert is_transient_llm_error(type("OverloadedError", (Exception,), {})("overloaded"))
    assert is_transient_llm_error(type("RateLimitError", (Exception,), {})("slow down"))
    assert is_transient_llm_error(type("InternalServerError", (Exception,), {})("500"))


@pytest.mark.unit
def test_bedrock_throttling_is_transient_and_validation_is_not():
    class ClientError(Exception):
        def __init__(self, code, status):
            super().__init__(code)
            self.response = {
                "Error": {"Code": code, "Message": code},
                "ResponseMetadata": {"HTTPStatusCode": status},
            }

    assert is_transient_llm_error(ClientError("ThrottlingException", 429))
    assert is_transient_llm_error(ClientError("ServiceUnavailableException", 503))
    assert not is_transient_llm_error(ClientError("ValidationException", 400))


@pytest.mark.unit
def test_backoff_grows_with_equal_jitter_and_caps(monkeypatch):
    monkeypatch.setattr("tradingagents.llm_clients.retry.random.uniform", lambda _a, b: b)
    unavailable = _unavailable()
    assert _wait_seconds(unavailable, 1) == 20
    assert _wait_seconds(unavailable, 2) == 40
    assert _wait_seconds(unavailable, 3) == 80
    assert _wait_seconds(unavailable, 4) == 120


@pytest.mark.unit
def test_retry_after_replaces_the_backoff_and_is_capped(monkeypatch):
    monkeypatch.setattr("tradingagents.llm_clients.retry.random.uniform", lambda _a, b: b)
    assert _wait_seconds(_Status(429, headers={"retry-after": "15"}), 1) == 15
    assert _wait_seconds(_Status(429, headers={"Retry-After": "600"}), 1) == 120
    # Gemini puts the delay in the error body, not a header.
    body = {"retryDelay": {"seconds": 25}}
    assert _wait_seconds(_Status(503, body=body), 1) == 25


@pytest.mark.unit
def test_sdk_retry_is_off_unless_the_caller_sets_a_budget():
    assert sdk_max_retries(None) == 0
    assert sdk_max_retries(None, google=True) == 1
    # Gemini treats 0 as "use the default fast retries".
    assert sdk_max_retries(0, google=True) == 1
    assert sdk_max_retries(6) == 6
    assert sdk_max_retries(6, google=True) == 6


@pytest.mark.unit
def test_constructed_clients_use_the_shared_schedule(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    from tradingagents.llm_clients.anthropic_client import AnthropicClient
    from tradingagents.llm_clients.google_client import GoogleClient
    from tradingagents.llm_clients.openai_client import OpenAIClient

    assert OpenAIClient("gpt-4.1", api_key="test").get_llm().max_retries == 0
    assert OpenAIClient("gpt-4.1", api_key="test", max_retries=6).get_llm().max_retries == 6
    assert GoogleClient("gemini-2.5-flash", api_key="test").get_llm().max_retries == 1
    assert AnthropicClient("claude-sonnet-4-5", api_key="test").get_llm().max_retries == 0


@pytest.mark.unit
def test_bedrock_chat_model_retries():
    pytest.importorskip("langchain_aws")
    from tradingagents.llm_clients.bedrock_client import _bedrock_class

    model_cls = _bedrock_class()
    assert "invoke_with_retry" in inspect.getsource(model_cls.invoke)


@pytest.mark.unit
def test_structured_fallback_does_not_swallow_a_503():
    from unittest.mock import MagicMock

    from tradingagents.agents.structured import invoke_structured_or_freetext

    structured = MagicMock()
    structured.invoke.side_effect = _unavailable()
    plain = MagicMock()

    with pytest.raises(GoogleAPIError, match="503"):
        invoke_structured_or_freetext(
            structured, plain, "prompt", render=lambda r: r, agent_name="Trader"
        )
    plain.invoke.assert_not_called()
