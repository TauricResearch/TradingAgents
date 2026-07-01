"""Tests for the long-horizon rate-limit retry layer (llm_clients.retry).

Covers the three pieces added after a deep run died on back-to-back 429s:

* error classification (retryable rate limit vs. permanent quota exhaustion),
* the wait/retry loop itself (schedule, retry-after, env knobs),
* the wiring: ``Normalized*`` chat clients retry through ``invoke``, and
  ``invoke_structured_or_freetext`` re-raises rate limits instead of
  burning its free-text fallback on a saturated provider.
"""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tradingagents.llm_clients import retry
from tradingagents.llm_clients.retry import (
    call_with_rate_limit_retry,
    is_quota_exhausted,
    is_rate_limit_error,
    is_retryable_rate_limit,
)

_ENV_KNOBS = (
    "TRADINGAGENTS_RATE_LIMIT_RETRIES",
    "TRADINGAGENTS_RATE_LIMIT_BASE_WAIT",
    "TRADINGAGENTS_RATE_LIMIT_MAX_WAIT",
)


class _FakeResponse:
    def __init__(self, status_code=429, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class _FakeStatusError(Exception):
    """Duck-typed stand-in for openai/anthropic APIStatusError."""

    def __init__(self, message="Error code: 429 - rate limited",
                 status_code=429, headers=None, code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = _FakeResponse(status_code, headers)
        if code is not None:
            self.code = code
        if body is not None:
            self.body = body


@pytest.fixture()
def sleeps(monkeypatch):
    """Neutralise time.sleep/jitter and record requested waits."""
    recorded = []
    monkeypatch.setattr(retry.time, "sleep", recorded.append)
    monkeypatch.setattr(retry.random, "uniform", lambda a, b: 0.0)
    for knob in _ENV_KNOBS:
        monkeypatch.delenv(knob, raising=False)
    return recorded


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClassification:
    def test_429_is_rate_limit(self):
        assert is_rate_limit_error(_FakeStatusError(status_code=429))

    def test_529_overloaded_is_rate_limit(self):
        assert is_rate_limit_error(_FakeStatusError(status_code=529))

    def test_other_status_is_not(self):
        assert not is_rate_limit_error(_FakeStatusError(status_code=500))

    def test_plain_exception_is_not(self):
        assert not is_rate_limit_error(ValueError("boom"))

    def test_status_read_from_response_when_missing_on_exc(self):
        exc = Exception("indirect")
        exc.response = _FakeResponse(status_code=429)
        assert is_rate_limit_error(exc)

    def test_quota_via_code_attribute(self):
        exc = _FakeStatusError(message="429", code="insufficient_quota")
        assert is_quota_exhausted(exc)
        assert not is_retryable_rate_limit(exc)

    def test_quota_via_flattened_body(self):
        # openai SDK sets exc.body to the inner error dict
        exc = _FakeStatusError(message="429", body={"code": "insufficient_quota"})
        assert is_quota_exhausted(exc)

    def test_quota_via_nested_body(self):
        exc = _FakeStatusError(
            message="429", body={"error": {"type": "insufficient_quota"}}
        )
        assert is_quota_exhausted(exc)

    def test_quota_via_message_only(self):
        exc = _FakeStatusError(message="429 insufficient_quota: check billing")
        assert is_quota_exhausted(exc)

    def test_ordinary_429_is_retryable(self):
        assert is_retryable_rate_limit(_FakeStatusError())


# ---------------------------------------------------------------------------
# Retry loop
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCallWithRateLimitRetry:
    def test_passthrough_on_success(self, sleeps):
        assert call_with_rate_limit_retry(lambda: "ok") == "ok"
        assert sleeps == []

    def test_retries_with_exponential_schedule(self, sleeps):
        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise _FakeStatusError()
            return "ok"

        assert call_with_rate_limit_retry(fn) == "ok"
        assert sleeps == [20.0, 40.0]

    def test_honors_retry_after_header(self, sleeps):
        calls = []

        def fn():
            calls.append(1)
            if len(calls) == 1:
                raise _FakeStatusError(headers={"retry-after": "7"})
            return "ok"

        assert call_with_rate_limit_retry(fn) == "ok"
        assert sleeps == [7.0]

    def test_retry_after_http_date(self, sleeps):
        when = datetime.now(timezone.utc) + timedelta(seconds=60)
        calls = []

        def fn():
            calls.append(1)
            if len(calls) == 1:
                raise _FakeStatusError(
                    headers={"retry-after": format_datetime(when, usegmt=True)}
                )
            return "ok"

        assert call_with_rate_limit_retry(fn) == "ok"
        assert len(sleeps) == 1 and 50.0 <= sleeps[0] <= 70.0

    def test_retry_after_capped_at_max_wait(self, sleeps, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_RATE_LIMIT_MAX_WAIT", "30")
        calls = []

        def fn():
            calls.append(1)
            if len(calls) == 1:
                raise _FakeStatusError(headers={"retry-after": "120"})
            return "ok"

        assert call_with_rate_limit_retry(fn) == "ok"
        assert sleeps == [30.0]

    def test_quota_exhaustion_never_retried(self, sleeps):
        fn = MagicMock(side_effect=_FakeStatusError(code="insufficient_quota"))
        with pytest.raises(_FakeStatusError):
            call_with_rate_limit_retry(fn)
        assert fn.call_count == 1
        assert sleeps == []

    def test_non_rate_limit_error_propagates(self, sleeps):
        fn = MagicMock(side_effect=ValueError("schema"))
        with pytest.raises(ValueError):
            call_with_rate_limit_retry(fn)
        assert fn.call_count == 1
        assert sleeps == []

    def test_raises_after_budget_exhausted(self, sleeps, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_RATE_LIMIT_RETRIES", "2")
        fn = MagicMock(side_effect=_FakeStatusError())
        with pytest.raises(_FakeStatusError):
            call_with_rate_limit_retry(fn)
        assert fn.call_count == 3  # initial + 2 retries
        assert len(sleeps) == 2

    def test_zero_retries_disables_layer(self, sleeps, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_RATE_LIMIT_RETRIES", "0")
        fn = MagicMock(side_effect=_FakeStatusError())
        with pytest.raises(_FakeStatusError):
            call_with_rate_limit_retry(fn)
        assert fn.call_count == 1
        assert sleeps == []


# ---------------------------------------------------------------------------
# structured-output fallback interaction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStructuredFallbackInteraction:
    def test_rate_limit_reraises_without_freetext_fallback(self):
        from tradingagents.agents.utils.structured import invoke_structured_or_freetext

        structured = MagicMock()
        structured.invoke.side_effect = _FakeStatusError()
        plain = MagicMock()

        with pytest.raises(_FakeStatusError):
            invoke_structured_or_freetext(
                structured, plain, "prompt", lambda r: "rendered", "Research Manager"
            )
        plain.invoke.assert_not_called()

    def test_format_errors_still_fall_back(self):
        from tradingagents.agents.utils.structured import invoke_structured_or_freetext

        structured = MagicMock()
        structured.invoke.side_effect = ValueError("malformed JSON")
        plain = MagicMock()
        plain.invoke.return_value = SimpleNamespace(content="free text")

        out = invoke_structured_or_freetext(
            structured, plain, "prompt", lambda r: "rendered", "Trader"
        )
        assert out == "free text"
        plain.invoke.assert_called_once_with("prompt")


# ---------------------------------------------------------------------------
# Client wiring: Normalized*.invoke rides out a 429
# ---------------------------------------------------------------------------


def _flaky_parent_invoke(returned_message):
    """Parent invoke that 429s once, then returns ``returned_message``."""
    state = {"calls": 0}

    def fake_invoke(self, input, config=None, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            raise _FakeStatusError()
        return returned_message

    return fake_invoke, state


@pytest.mark.unit
class TestClientWiring:
    def test_anthropic_invoke_retries_and_normalizes(self, sleeps, monkeypatch):
        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import AIMessage

        from tradingagents.llm_clients.anthropic_client import NormalizedChatAnthropic

        message = AIMessage(content=[{"type": "text", "text": "ok"}])
        fake_invoke, state = _flaky_parent_invoke(message)
        monkeypatch.setattr(ChatAnthropic, "invoke", fake_invoke)

        llm = NormalizedChatAnthropic(model="claude-sonnet-4-5", api_key="test")
        result = llm.invoke("hello")

        assert state["calls"] == 2
        assert sleeps == [20.0]
        assert result.content == "ok"

    def test_openai_invoke_retries_and_normalizes(self, sleeps, monkeypatch):
        from langchain_core.messages import AIMessage
        from langchain_openai import ChatOpenAI

        from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI

        message = AIMessage(content=[{"type": "text", "text": "ok"}])
        fake_invoke, state = _flaky_parent_invoke(message)
        monkeypatch.setattr(ChatOpenAI, "invoke", fake_invoke)

        llm = NormalizedChatOpenAI(model="gpt-5.5", api_key="test")
        result = llm.invoke("hello")

        assert state["calls"] == 2
        assert sleeps == [20.0]
        assert result.content == "ok"
