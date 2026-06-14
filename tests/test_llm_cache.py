"""Tests for the LLM response cache module.

These tests exercise the core ``LLMResponseCache`` class as well as the
module‑level helper functions.  Real file I/O is used (isolated inside a
temporary directory) so we're testing the actual serialisation round‑trip,
not a mock.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from tradingagents.llm_clients.llm_cache import (
    LLMResponseCache,
    _aimessage_to_dict,
    _build_cache_key,
    _dict_to_aimessage,
    _normalise_input,
    _safe_metadata,
    _serialise_messages,
)


# ---------------------------------------------------------------------------
# Unit tests — serialisation helpers
# ---------------------------------------------------------------------------

class TestSerialiseMessages:
    """``_serialise_messages`` produces deterministic JSON."""

    def test_base_message_list(self) -> None:
        msgs = [
            AIMessage(content="Hello"),
            AIMessage(content="World", additional_kwargs={"reasoning_content": "thinking..."}),
        ]
        result = _serialise_messages(msgs)
        loaded = json.loads(result)
        assert len(loaded) == 2
        assert loaded[0]["role"] == "ai"
        assert loaded[0]["content"] == "Hello"

    def test_deterministic(self) -> None:
        a = _serialise_messages([AIMessage(content="Hi")])
        b = _serialise_messages([AIMessage(content="Hi")])
        assert a == b

    def test_different_content_gives_different_json(self) -> None:
        a = _serialise_messages([AIMessage(content="Alpha")])
        b = _serialise_messages([AIMessage(content="Beta")])
        assert a != b

    def test_empty_list(self) -> None:
        assert _serialise_messages([]) == "[]"

    def test_dict_input(self) -> None:
        msgs = [{"role": "user", "content": "hello"}]
        result = _serialise_messages(msgs)
        assert json.loads(result) == [{"role": "user", "content": "hello"}]

    def test_raw_string_input(self) -> None:
        # A bare string is normalised to a single‑message list, not per‑character.
        result = _serialise_messages("raw string")
        loaded = json.loads(result)
        assert len(loaded) == 1
        assert loaded[0]["role"] == ""
        assert loaded[0]["content"] == "raw string"


class TestNormaliseInput:
    """``_normalise_input`` guards against string iteration and PromptValue errors."""

    def test_string_becomes_single_element_list(self) -> None:
        normalised = _normalise_input("hello")
        assert normalised == ["hello"]

    def test_list_passes_through(self) -> None:
        normalised = _normalise_input(["a", "b"])
        assert normalised == ["a", "b"]

    def test_promptvalue_calls_to_messages(self) -> None:
        class FakePromptValue:
            def to_messages(self):
                return [AIMessage(content="from prompt value")]
        normalised = _normalise_input(FakePromptValue())
        assert len(normalised) == 1
        assert normalised[0].content == "from prompt value"

    def test_other_object_wrapped_in_list(self) -> None:
        normalised = _normalise_input(42)
        assert normalised == [42]


class TestBuildCacheKey:
    """Cache key determinism and collision resistance."""

    def test_same_input_same_key(self) -> None:
        msgs = [AIMessage(content="Test")]
        k1 = _build_cache_key("deepseek-v4-flash", msgs, 0.0)
        k2 = _build_cache_key("deepseek-v4-flash", msgs, 0.0)
        assert k1 == k2

    def test_different_model_different_key(self) -> None:
        msgs = [AIMessage(content="Test")]
        k1 = _build_cache_key("deepseek-v4-flash", msgs)
        k2 = _build_cache_key("gpt-4", msgs)
        assert k1 != k2

    def test_different_messages_different_key(self) -> None:
        k1 = _build_cache_key("m", [AIMessage(content="A")])
        k2 = _build_cache_key("m", [AIMessage(content="B")])
        assert k1 != k2

    def test_key_is_sha256(self) -> None:
        key = _build_cache_key("m", [AIMessage(content="x")])
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_different_tools_different_key(self) -> None:
        msgs = [AIMessage(content="Test")]
        k1 = _build_cache_key("m", msgs, tools=[{"type": "function", "function": {"name": "weather"}}])
        k2 = _build_cache_key("m", msgs, tools=[{"type": "function", "function": {"name": "stock"}}])
        assert k1 != k2

    def test_different_response_format_different_key(self) -> None:
        msgs = [AIMessage(content="Test")]
        k1 = _build_cache_key("m", msgs, response_format={"type": "json_object"})
        k2 = _build_cache_key("m", msgs, response_format={"type": "text"})
        assert k1 != k2

    def test_kwargs_none_ignored(self) -> None:
        msgs = [AIMessage(content="Test")]
        k1 = _build_cache_key("m", msgs, tools=None, tool_choice=None)
        k2 = _build_cache_key("m", msgs)
        assert k1 == k2


class TestSafeMetadata:
    """``_safe_metadata`` strips non‑serialisable keys."""

    def test_strips_headers(self) -> None:
        raw = {"headers": {"x-request-id": "abc"}, "token_usage": {"total": 100}}
        cleaned = _safe_metadata(raw)
        assert "headers" not in cleaned
        assert cleaned["token_usage"] == {"total": 100}

    def test_strips_raw_response(self) -> None:
        raw = {"raw_response": object(), "model": "gpt-4"}
        cleaned = _safe_metadata(raw)
        assert "raw_response" not in cleaned

    def test_none_input(self) -> None:
        assert _safe_metadata(None) == {}

    def test_empty_dict(self) -> None:
        assert _safe_metadata({}) == {}


class TestAIMessageRoundTrip:
    """Serialising and deserialising preserves semantic content."""

    def _roundtrip(self, original: AIMessage) -> AIMessage:
        d = _aimessage_to_dict(original)
        return _dict_to_aimessage(d)

    def test_content_preserved(self) -> None:
        msg = AIMessage(content="Hello world")
        restored = self._roundtrip(msg)
        assert restored.content == "Hello world"

    def test_additional_kwargs_preserved(self) -> None:
        msg = AIMessage(content="Hi", additional_kwargs={"reasoning_content": "..."})
        restored = self._roundtrip(msg)
        assert restored.additional_kwargs["reasoning_content"] == "..."

    def test_tool_calls_preserved(self) -> None:
        msg = AIMessage(
            content="",
            tool_calls=[{"name": "get_stock", "args": {"symbol": "NVDA"}, "id": "call_1"}],
        )
        restored = self._roundtrip(msg)
        assert len(restored.tool_calls) == 1
        assert restored.tool_calls[0]["name"] == "get_stock"

    def test_usage_metadata_preserved(self) -> None:
        msg = AIMessage(content="Hi", usage_metadata={"input_tokens": 10, "output_tokens": 5})
        restored = self._roundtrip(msg)
        assert restored.usage_metadata["input_tokens"] == 10

    def test_missing_fields_default_gracefully(self) -> None:
        restored = _dict_to_aimessage({"content": "Hello"})
        assert restored.content == "Hello"
        assert restored.additional_kwargs == {}
        assert restored.tool_calls == []


# ---------------------------------------------------------------------------
# Integration tests — LLMResponseCache (real file I/O)
# ---------------------------------------------------------------------------

class TestLLMResponseCache:
    """Integration tests against the real filesystem inside a tmpdir."""

    @pytest.fixture(autouse=True)
    def _tmp_cache(self, tmp_path: Path) -> None:
        self.cache = LLMResponseCache(str(tmp_path), ttl_hours=24)
        self.cache_dir = tmp_path / "llm_responses"

    # -- get/set -----------------------------------------------------------

    def test_miss_returns_none(self) -> None:
        assert self.cache.get("nonexistent") is None

    def test_set_and_get(self) -> None:
        msg = AIMessage(content="Cached response")
        self.cache.set("key1", msg)
        restored = self.cache.get("key1")
        assert restored is not None
        assert restored.content == "Cached response"

    def test_set_and_get_with_metadata(self) -> None:
        msg = AIMessage(
            content="Analysis result",
            additional_kwargs={"reasoning_content": "step by step"},
            response_metadata={"model": "deepseek-v4-flash", "token_usage": {"total": 50}},
        )
        self.cache.set("key2", msg)
        restored = self.cache.get("key2")
        assert restored is not None
        assert restored.additional_kwargs["reasoning_content"] == "step by step"
        assert restored.response_metadata["model"] == "deepseek-v4-flash"

    def test_overwrite_existing_key(self) -> None:
        self.cache.set("k", AIMessage(content="v1"))
        self.cache.set("k", AIMessage(content="v2"))
        assert self.cache.get("k") is not None
        assert self.cache.get("k").content == "v2"

    def test_hit_and_miss_counters(self) -> None:
        self.cache.set("h", AIMessage(content="hit"))
        self.cache.get("h")   # hit
        self.cache.get("x")   # miss
        self.cache.get("y")   # miss
        assert self.cache.hits == 1
        assert self.cache.misses == 2

    # -- TTL expiry --------------------------------------------------------

    def test_expired_entry_returns_none(self) -> None:
        self.cache.set("exp", AIMessage(content="will expire"))
        # Artificially age the file.
        path = self.cache_dir / "exp.json"
        old = time.time() - (25 * 3600)  # 25 hours ago
        os.utime(path, (old, old))
        assert self.cache.get("exp") is None

    def test_expired_file_is_deleted(self) -> None:
        self.cache.set("del", AIMessage(content="bye"))
        path = self.cache_dir / "del.json"
        old = time.time() - (25 * 3600)
        os.utime(path, (old, old))
        self.cache.get("del")
        assert not path.exists()

    # -- clear -------------------------------------------------------------

    def test_clear_all(self) -> None:
        self.cache.set("a", AIMessage(content="1"))
        self.cache.set("b", AIMessage(content="2"))
        removed = self.cache.clear_all()
        assert removed == 2
        assert self.cache.get("a") is None
        # Counters are reset.
        assert self.cache.hits == 0
        assert self.cache.misses == 0

    def test_clear_expired(self) -> None:
        self.cache.set("fresh", AIMessage(content="new"))
        self.cache.set("old", AIMessage(content="stale"))
        old_time = time.time() - (25 * 3600)
        os.utime(self.cache_dir / "old.json", (old_time, old_time))
        removed = self.cache.clear_expired()
        assert removed == 1
        assert self.cache_dir / "fresh.json"  # still exists
        assert not (self.cache_dir / "old.json").exists()

    # -- stats -------------------------------------------------------------

    def test_stats_empty(self) -> None:
        stats = self.cache.stats()
        assert stats["entry_count"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["hit_rate"] == 0.0

    def test_stats_after_operations(self) -> None:
        self.cache.set("s1", AIMessage(content="stats1"))
        self.cache.set("s2", AIMessage(content="stats2"))
        self.cache.get("s1")   # hit
        self.cache.get("s1")   # hit
        self.cache.get("nope") # miss
        stats = self.cache.stats()
        assert stats["entry_count"] == 2
        assert stats["total_size_bytes"] > 0
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 2.0 / 3.0
        assert stats["ttl_hours"] == 24
        assert stats["cache_dir"] == str(self.cache_dir)

    # -- corrupt file handling ---------------------------------------------

    def test_corrupt_file_returns_none_and_deletes(self) -> None:
        self.cache.set("ok", AIMessage(content="fine"))
        # Write garbage over the file.
        (self.cache_dir / "ok.json").write_text("{bad json", encoding="utf-8")
        assert self.cache.get("ok") is None
        assert not (self.cache_dir / "ok.json").exists()

    # -- fault tolerance -----------------------------------------------------

    def test_get_handles_oserror(self, monkeypatch) -> None:
        self.cache.set("ft1", AIMessage(content="test"))
        # Simulate a permission error on read.
        def _failing_read_text(*args, **kwargs):
            raise OSError("Permission denied")
        monkeypatch.setattr(Path, "read_text", _failing_read_text)
        # Must not raise.
        assert self.cache.get("ft1") is None

    def test_set_handles_serialisation_error(self, monkeypatch) -> None:
        # Simulate json.dumps failing.
        import json as json_module
        def _failing_dumps(*args, **kwargs):
            raise TypeError("Cannot serialise")
        monkeypatch.setattr(json_module, "dumps", _failing_dumps)
        # Must not raise.
        self.cache.set("ft2", AIMessage(content="test"))

    def test_set_handles_oserror(self, monkeypatch) -> None:
        def _failing_write_text(*args, **kwargs):
            raise OSError("Disk full")
        monkeypatch.setattr(Path, "write_text", _failing_write_text)
        # Must not raise.
        self.cache.set("ft3", AIMessage(content="test"))


# ---------------------------------------------------------------------------
# Module‑level helper tests
# ---------------------------------------------------------------------------

class TestModuleHelpers:
    """``should_cache_provider``, ``check_cache``, ``store_cache``."""

    def test_should_cache_provider_empty_allowed_list(self) -> None:
        with patch(
            "tradingagents.llm_clients.llm_cache._get_config",
            return_value={"llm_cache_providers": []},
        ):
            from tradingagents.llm_clients.llm_cache import should_cache_provider
            assert should_cache_provider("deepseek") is True
            assert should_cache_provider("ollama") is True

    def test_should_cache_provider_filtered(self) -> None:
        with patch(
            "tradingagents.llm_clients.llm_cache._get_config",
            return_value={"llm_cache_providers": ["deepseek", "openai"]},
        ):
            from tradingagents.llm_clients.llm_cache import should_cache_provider
            assert should_cache_provider("deepseek") is True
            assert should_cache_provider("openai") is True
            assert should_cache_provider("ollama") is False
            assert should_cache_provider("anthropic") is False

    def test_should_cache_provider_case_insensitive(self) -> None:
        with patch(
            "tradingagents.llm_clients.llm_cache._get_config",
            return_value={"llm_cache_providers": ["DeepSeek", "OPENAI"]},
        ):
            from tradingagents.llm_clients.llm_cache import should_cache_provider
            assert should_cache_provider("deepseek") is True
            assert should_cache_provider("OpenAI") is True


# ---------------------------------------------------------------------------
# Smoke test: env-var overrides for cache config
# ---------------------------------------------------------------------------

class TestCacheEnvOverrides:
    """``TRADINGAGENTS_LLM_CACHE_ENABLED`` and friends."""

    def test_cache_enabled_default(self, monkeypatch) -> None:
        import importlib
        import tradingagents.default_config as dc_mod
        dc = importlib.reload(dc_mod)
        assert dc.DEFAULT_CONFIG["llm_cache_enabled"] is True
        assert dc.DEFAULT_CONFIG["llm_cache_ttl_hours"] == 24
        assert dc.DEFAULT_CONFIG["llm_cache_providers"] == []

    def test_cache_disabled_via_env(self, monkeypatch) -> None:
        import importlib
        import tradingagents.default_config as dc_mod
        for key in list(dc_mod._ENV_OVERRIDES):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TRADINGAGENTS_LLM_CACHE_ENABLED", "false")
        dc = importlib.reload(dc_mod)
        assert dc.DEFAULT_CONFIG["llm_cache_enabled"] is False

    def test_cache_ttl_via_env(self, monkeypatch) -> None:
        import importlib
        import tradingagents.default_config as dc_mod
        for key in list(dc_mod._ENV_OVERRIDES):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TRADINGAGENTS_LLM_CACHE_TTL_HOURS", "48")
        dc = importlib.reload(dc_mod)
        assert dc.DEFAULT_CONFIG["llm_cache_ttl_hours"] == 48

    def test_cache_providers_via_env(self, monkeypatch) -> None:
        import importlib
        import tradingagents.default_config as dc_mod
        for key in list(dc_mod._ENV_OVERRIDES):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TRADINGAGENTS_LLM_CACHE_PROVIDERS", "deepseek,openai")
        dc = importlib.reload(dc_mod)
        assert dc.DEFAULT_CONFIG["llm_cache_providers"] == ["deepseek", "openai"]
