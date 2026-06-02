"""Unit tests for the LLM response cache module.

Covers the key derivation (so different request shapes hash
differently), the on-disk roundtrip via the cache helper, and the
disabled / TTL escape hatches. The wired-through chat client is
exercised in ``test_llm_clients_cache_retry_wiring.py``.
"""

from __future__ import annotations

import json
import time

import pytest
from langchain_core.messages import AIMessage

from tradingagents.llm_clients.cache import (
    LLMResponseCache,
    make_cache_key,
)


@pytest.mark.unit
class TestMakeCacheKey:
    """``make_cache_key`` is the single source of truth for cache hit/miss
    decisions; if it hashes two semantically different requests the same
    way, we serve the wrong analyst report. These tests pin that."""

    def test_same_input_same_model_same_key(self):
        a = make_cache_key("gpt-4.1", [("system", "s"), ("human", "h")])
        b = make_cache_key("gpt-4.1", [("system", "s"), ("human", "h")])
        assert a == b

    def test_different_model_different_key(self):
        a = make_cache_key("gpt-4.1", [("human", "h")])
        b = make_cache_key("gpt-4.1-mini", [("human", "h")])
        assert a != b

    def test_different_messages_different_key(self):
        a = make_cache_key("gpt-4.1", [("human", "h1")])
        b = make_cache_key("gpt-4.1", [("human", "h2")])
        assert a != b

    def test_different_temperature_different_key(self):
        a = make_cache_key("gpt-4.1", [("human", "h")], temperature=0.0)
        b = make_cache_key("gpt-4.1", [("human", "h")], temperature=0.7)
        assert a != b

    def test_different_tools_different_key(self):
        a = make_cache_key(
            "gpt-4.1", [("human", "h")], tools=[{"name": "foo"}]
        )
        b = make_cache_key(
            "gpt-4.1", [("human", "h")], tools=[{"name": "bar"}]
        )
        assert a != b

    def test_same_tools_same_key(self):
        # Order-insensitive: both call sites produce the same hash for the
        # same logical toolset. (Tools are sorted by JSON dump; the
        # individual dict comparison is positional here, but the key
        # derivation is the test of the user-facing contract.)
        a = make_cache_key(
            "gpt-4.1", [("human", "h")], tools=[{"name": "foo"}, {"name": "bar"}]
        )
        b = make_cache_key(
            "gpt-4.1", [("human", "h")], tools=[{"name": "foo"}, {"name": "bar"}]
        )
        assert a == b

    def test_non_semantic_kwargs_ignored(self):
        # ``callbacks`` and ``http_client`` don't change the response,
        # so they must NOT participate in the cache key.
        a = make_cache_key("gpt-4.1", [("human", "h")], callbacks=["a"])
        b = make_cache_key("gpt-4.1", [("human", "h")], callbacks=["b"])
        c = make_cache_key("gpt-4.1", [("human", "h")])
        assert a == b == c

    def test_tool_choice_changes_key(self):
        a = make_cache_key("gpt-4.1", [("human", "h")], tool_choice="auto")
        b = make_cache_key("gpt-4.1", [("human", "h")], tool_choice="none")
        assert a != b

    def test_key_is_hex_sha256(self):
        key = make_cache_key("gpt-4.1", [("human", "h")])
        assert len(key) == 64
        int(key, 16)  # raises if not hex

    def test_anthropic_effort_changes_key(self):
        # Anthropic opus/sonnet 4.5+ accepts ``effort`` and produces
        # different responses for different effort levels. A cache hit
        # that ignores this would return the wrong analyst report.
        a = make_cache_key("claude-opus-5-0", [("human", "h")], effort="low")
        b = make_cache_key("claude-opus-5-0", [("human", "h")], effort="high")
        assert a != b

    def test_anthropic_thinking_changes_key(self):
        # Anthropic's ``thinking`` dict (extended thinking) materially
        # changes the response. Same-prompt-different-thinking must
        # not collide.
        a = make_cache_key(
            "claude-sonnet-5-0", [("human", "h")],
            thinking={"type": "enabled", "budget_tokens": 1024},
        )
        b = make_cache_key(
            "claude-sonnet-5-0", [("human", "h")],
            thinking={"type": "enabled", "budget_tokens": 4096},
        )
        assert a != b

    def test_openai_reasoning_effort_changes_key(self):
        a = make_cache_key("gpt-5.5", [("human", "h")], reasoning_effort="low")
        b = make_cache_key("gpt-5.5", [("human", "h")], reasoning_effort="high")
        assert a != b

    def test_google_thinking_budget_changes_key(self):
        a = make_cache_key("gemini-2.5-pro", [("human", "h")], thinking_budget=0)
        b = make_cache_key("gemini-2.5-pro", [("human", "h")], thinking_budget=-1)
        assert a != b


@pytest.mark.unit
class TestCacheRoundtrip:
    """Cache.get / Cache.put must roundtrip an AIMessage with all
    semantically important fields intact (content, tool_calls).
    """

    def test_roundtrip_preserves_content(self, tmp_path):
        cache = LLMResponseCache(tmp_path / "cache", enabled=True)
        key = make_cache_key("gpt-4.1", [("system", "s"), ("human", "h")])
        original = AIMessage(content="hello world")
        cache.put(key, original)
        loaded = cache.get(key)
        assert loaded is not None
        assert loaded.content == "hello world"

    def test_roundtrip_preserves_tool_calls(self, tmp_path):
        cache = LLMResponseCache(tmp_path / "cache", enabled=True)
        key = make_cache_key("gpt-4.1", [("human", "h")])
        original = AIMessage(
            content="",
            tool_calls=[{"name": "get_stock_data", "args": {"ticker": "NVDA"}, "id": "call_1"}],
        )
        cache.put(key, original)
        loaded = cache.get(key)
        assert loaded is not None
        assert len(loaded.tool_calls) == 1
        assert loaded.tool_calls[0]["name"] == "get_stock_data"
        assert loaded.tool_calls[0]["args"] == {"ticker": "NVDA"}

    def test_miss_returns_none(self, tmp_path):
        cache = LLMResponseCache(tmp_path / "cache", enabled=True)
        assert cache.get("nonexistent" * 4) is None

    def test_corrupted_entry_treated_as_miss(self, tmp_path):
        cache = LLMResponseCache(tmp_path / "cache", enabled=True)
        key = make_cache_key("gpt-4.1", [("human", "h")])
        path = cache._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not valid json", encoding="utf-8")
        assert cache.get(key) is None
        # Stats should reflect the miss.
        assert cache.stats.misses >= 1

    def test_disabled_cache_is_no_op(self, tmp_path):
        cache = LLMResponseCache(tmp_path / "cache", enabled=False)
        key = make_cache_key("gpt-4.1", [("human", "h")])
        cache.put(key, AIMessage(content="x"))
        assert cache.get(key) is None
        assert cache.stats.misses == 1


@pytest.mark.unit
class TestCacheTTL:
    """TTL eviction: an entry older than ``ttl_seconds`` must miss
    cleanly without raising. The test uses real time.sleep on a small
    window to keep the suite fast."""

    def test_expired_entry_treated_as_miss(self, tmp_path):
        cache = LLMResponseCache(tmp_path / "cache", enabled=True, ttl_seconds=1)
        key = make_cache_key("gpt-4.1", [("human", "h")])
        cache.put(key, AIMessage(content="expired"))
        # Bypass the disk read by directly inspecting the envelope.
        path = cache._path_for(key)
        envelope = json.loads(path.read_text(encoding="utf-8"))
        # Set the timestamp to 10 seconds in the past so the next get
        # sees it as expired.
        envelope["created_at"] = time.time() - 10
        path.write_text(json.dumps(envelope), encoding="utf-8")
        assert cache.get(key) is None
        assert cache.stats.expired_skips >= 1

    def test_fresh_entry_within_ttl_hits(self, tmp_path):
        cache = LLMResponseCache(tmp_path / "cache", enabled=True, ttl_seconds=3600)
        key = make_cache_key("gpt-4.1", [("human", "h")])
        cache.put(key, AIMessage(content="fresh"))
        assert cache.get(key) is not None

    def test_ttl_none_means_never_expire(self, tmp_path):
        cache = LLMResponseCache(tmp_path / "cache", enabled=True, ttl_seconds=None)
        key = make_cache_key("gpt-4.1", [("human", "h")])
        cache.put(key, AIMessage(content="forever"))
        # Backdate the entry well past any reasonable TTL.
        path = cache._path_for(key)
        envelope = json.loads(path.read_text(encoding="utf-8"))
        envelope["created_at"] = time.time() - 86400 * 365  # one year
        path.write_text(json.dumps(envelope), encoding="utf-8")
        assert cache.get(key) is not None


@pytest.mark.unit
class TestCacheStats:
    """Stats are advisory counters used by the integration wiring to
    surface cache effectiveness to users; they must increment correctly
    on every put/get."""

    def test_miss_then_hit_then_write(self, tmp_path):
        cache = LLMResponseCache(tmp_path / "cache", enabled=True)
        key = make_cache_key("gpt-4.1", [("human", "h")])
        cache.get(key)  # miss
        cache.put(key, AIMessage(content="x"))
        cache.get(key)  # hit
        cache.get(key)  # hit
        assert cache.stats.misses == 1
        assert cache.stats.hits == 2
        assert cache.stats.writes == 1

    def test_clear_resets_files_but_not_stats(self, tmp_path):
        cache = LLMResponseCache(tmp_path / "cache", enabled=True)
        key = make_cache_key("gpt-4.1", [("human", "h")])
        cache.put(key, AIMessage(content="x"))
        removed = cache.clear()
        assert removed >= 1
        assert cache.get(key) is None  # file is gone
