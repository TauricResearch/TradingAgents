"""Wiring tests: cache + retry are attached to chat clients via
``create_llm_client(..., llm_cache=..., retry_policy=...)`` and route
``invoke`` through the wrapper when configured.

End-to-end retry behavior (real 429 -> sleep -> retry -> success) is
also covered here because that's the user-facing contract.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from openai import RateLimitError

from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.cache import LLMResponseCache, make_cache_key
from tradingagents.llm_clients.retry import RetryPolicy


def _fake_resp(code, headers=None):
    r = MagicMock()
    r.status_code = code
    r.headers = headers or {}
    return r


def _make_429(retry_after="1"):
    return RateLimitError(
        "rate", response=_fake_resp(429, {"retry-after": retry_after}), body=None
    )


@pytest.mark.unit
class TestOpenAIClientWiring:
    def test_cache_and_policy_are_attached(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        cache = LLMResponseCache(".tmp_wiring_cache", enabled=True)
        policy = RetryPolicy(max_retries=2, base_delay_seconds=0.0, max_delay_seconds=0.0, jitter=0.0, sleep=lambda s: None)
        client = create_llm_client(
            provider="openai", model="gpt-4.1", api_key="sk-test",
            llm_cache=cache, retry_policy=policy,
        )
        chat = client.get_llm()
        assert chat._llm_cache is cache
        assert chat._retry_policy is policy
        assert hasattr(chat, "_base_invoke")  # captured at __init__

    def test_no_cache_or_policy_means_no_attributes(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        client = create_llm_client(provider="openai", model="gpt-4.1", api_key="sk-test")
        chat = client.get_llm()
        # Without kwargs, the wiring is a no-op: the chat still works
        # via the original (un-wrapped) path.
        assert not hasattr(chat, "_llm_cache")
        assert not hasattr(chat, "_retry_policy")
        assert hasattr(chat, "_base_invoke")

    def test_cache_hit_avoids_re_invoke(self, monkeypatch):
        """The user-facing contract: same prompt twice = one network call."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        cache = LLMResponseCache(".tmp_wiring_cache", enabled=True)
        cache.clear()
        policy = RetryPolicy(max_retries=0, base_delay_seconds=0.0, max_delay_seconds=0.0, jitter=0.0)
        client = create_llm_client(
            provider="openai", model="gpt-4.1", api_key="sk-test",
            llm_cache=cache, retry_policy=policy,
        )
        chat = client.get_llm()

        # ``_base_invoke`` is captured at __init__ as a bound method
        # to the real ``ChatOpenAI.invoke``. We can't replace it via
        # ``patch.object(ChatOpenAI, "invoke", ...)`` because the bound
        # method already holds the function reference. Instead, swap
        # the bound method on the instance with a recording stub.
        real_calls = []
        def fake_invoke(input, config=None, **kwargs):
            real_calls.append(input)
            return AIMessage(content=f"response #{len(real_calls)}")

        with patch.object(chat, "_base_invoke", side_effect=fake_invoke):
            r1 = chat.invoke([("system", "s"), ("human", "hi")])
            r2 = chat.invoke([("system", "s"), ("human", "hi")])
            r3 = chat.invoke([("system", "s"), ("human", "hi 2")])

        assert r1.content == "response #1"
        assert r2.content == "response #1"  # cache hit
        assert r3.content == "response #2"  # new key
        assert len(real_calls) == 2
        assert cache.stats.hits == 1
        cache.clear()

    def test_retry_then_success_path(self, monkeypatch):
        """A 429 from the underlying API must trigger retry, then succeed."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        cache = LLMResponseCache(".tmp_wiring_cache", enabled=True)
        cache.clear()
        sleeps = []
        # max_delay_seconds intentionally non-zero: the policy's cap
        # applies to Retry-After too, and we want to assert the value
        # the server sent (2.0) was honored. ``sleep=sleeps.append``
        # stubs out real time so nothing actually blocks.
        policy = RetryPolicy(
            max_retries=3, base_delay_seconds=1.0, max_delay_seconds=10.0,
            jitter=0.0, sleep=sleeps.append,
        )
        client = create_llm_client(
            provider="openai", model="gpt-4.1", api_key="sk-test",
            llm_cache=cache, retry_policy=policy,
        )
        chat = client.get_llm()

        real_calls = []
        def fake_invoke(input, config=None, **kwargs):
            real_calls.append(input)
            if len(real_calls) < 3:
                raise _make_429("2")
            return AIMessage(content="eventually ok")

        with patch.object(chat, "_base_invoke", side_effect=fake_invoke):
            r = chat.invoke([("system", "s"), ("human", "retry-me")])

        assert r.content == "eventually ok"
        assert len(real_calls) == 3
        assert sleeps == [2.0, 2.0]  # Retry-After honored on each retry
        cache.clear()

    def test_429_exhausts_retries_then_raises(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        cache = LLMResponseCache(".tmp_wiring_cache", enabled=True)
        cache.clear()
        policy = RetryPolicy(
            max_retries=2, base_delay_seconds=0.0, max_delay_seconds=0.0,
            jitter=0.0, sleep=lambda s: None,
        )
        client = create_llm_client(
            provider="openai", model="gpt-4.1", api_key="sk-test",
            llm_cache=cache, retry_policy=policy,
        )
        chat = client.get_llm()

        def always_429(input, config=None, **kwargs):
            raise _make_429("1")

        with patch.object(chat, "_base_invoke", side_effect=always_429):
            with pytest.raises(RateLimitError):
                chat.invoke([("system", "s"), ("human", "perm-429")])
        cache.clear()

    def test_non_retryable_propagates_immediately(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        cache = LLMResponseCache(".tmp_wiring_cache", enabled=True)
        cache.clear()
        policy = RetryPolicy(
            max_retries=3, base_delay_seconds=0.0, max_delay_seconds=0.0,
            jitter=0.0, sleep=lambda s: None,
        )
        client = create_llm_client(
            provider="openai", model="gpt-4.1", api_key="sk-test",
            llm_cache=cache, retry_policy=policy,
        )
        chat = client.get_llm()

        calls = []
        def value_error(input, config=None, **kwargs):
            calls.append(input)
            raise ValueError("config bug")

        with patch.object(chat, "_base_invoke", side_effect=value_error):
            with pytest.raises(ValueError):
                chat.invoke([("system", "s"), ("human", "bad")])
        assert len(calls) == 1  # no retry
        cache.clear()
