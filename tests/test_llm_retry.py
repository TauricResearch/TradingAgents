"""Unit tests for ``NormalizedChatOpenAI.invoke`` transient-failure retry.

The retry loop wraps ``super().invoke()`` and retries only an undecodable JSON
response body (``json.JSONDecodeError``) — the one transient failure the OpenAI
SDK does not retry itself. The HTTP-transient family is delegated to the SDK,
and permanent errors surface immediately. These tests exercise that loop
directly by stubbing the parent ``invoke``.
"""

import json

import httpx
import openai
import pytest

import tradingagents.llm_clients.openai_client as oc


@pytest.fixture(autouse=True)
def _fast_and_isolated(monkeypatch):
    # Don't actually sleep between retries, and don't require a real message
    # object back from the (stubbed) parent invoke.
    monkeypatch.setattr(oc.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(oc, "normalize_content", lambda value: value)


def _client(max_retries):
    # Build an instance without network/credentials; we only exercise the retry
    # loop, which reads ``self.max_retries`` and calls ``super().invoke()``.
    return oc.NormalizedChatOpenAI.model_construct(max_retries=max_retries)


def test_transient_failure_is_retried_then_succeeds(monkeypatch):
    calls = []

    def flaky(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise json.JSONDecodeError("Expecting value", "", 0)
        return "recovered"

    monkeypatch.setattr(oc.ChatOpenAI, "invoke", flaky)
    assert _client(max_retries=2).invoke("prompt") == "recovered"
    assert len(calls) == 2  # one transient failure, then success


def test_permanent_error_is_not_retried(monkeypatch):
    calls = []

    def boom(self, *args, **kwargs):
        calls.append(1)
        raise ValueError("permanent 4xx-style failure")

    monkeypatch.setattr(oc.ChatOpenAI, "invoke", boom)
    with pytest.raises(ValueError):
        _client(max_retries=5).invoke("prompt")
    assert len(calls) == 1  # surfaced immediately, never retried


def test_persistent_transient_exhausts_budget_then_raises(monkeypatch):
    calls = []

    def always_transient(self, *args, **kwargs):
        calls.append(1)
        raise json.JSONDecodeError("Expecting value", "", 0)

    monkeypatch.setattr(oc.ChatOpenAI, "invoke", always_transient)
    with pytest.raises(json.JSONDecodeError):
        _client(max_retries=2).invoke("prompt")
    assert len(calls) == 3  # initial attempt + max_retries


def test_http_transient_is_delegated_to_the_sdk_not_outer_retried(monkeypatch):
    # The OpenAI SDK retries the connection / timeout / 5xx / 429 family itself
    # (max_retries is forwarded to it), so the invoke loop must NOT also catch
    # those — that would multiply requests. An HTTP-family error therefore
    # propagates on the first attempt instead of being re-retried here.
    calls = []

    def http_transient(self, *args, **kwargs):
        calls.append(1)
        raise openai.APITimeoutError(
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        )

    monkeypatch.setattr(oc.ChatOpenAI, "invoke", http_transient)
    with pytest.raises(openai.APITimeoutError):
        _client(max_retries=3).invoke("prompt")
    assert len(calls) == 1  # delegated to the SDK, not re-retried at invoke level
