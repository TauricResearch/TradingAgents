"""Tests for per-model pricing catalog and per-call cost estimation.

The catalog is the single source of truth for what each model costs
in the dashboard's cost estimate. These tests pin the contract so:

* Adding/removing a model in ``model_catalog.MODEL_OPTIONS`` surfaces
  as a stale-pricing test failure (the parametrize list is generated
  from the catalog).
* Renaming a model or provider key trips the call-site assertions.
* The callback handler returns the expected per-model buckets for a
  realistic mixed-provider LangChain run.
* The LiteLLM overlay fetcher gracefully degrades to the local
  catalog on every failure mode (no network, no httpx, bad payload,
  shrunk payload, corrupt cache).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from cli.stats_handler import (
    StatsCallbackHandler,
    _extract_model_name,
    _parse_price,
)
from tradingagents.llm_clients import pricing
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
from tradingagents.llm_clients.pricing import (
    PRICING,
    _load_litellm_overlay,
    _parse_litellm_payload,
    get_price,
    get_price_for_model,
)

class _TempDirMixin:
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(str(self._tmp), ignore_errors=True)


# ---- Catalog coverage -----------------------------------------------------


def _catalog_models() -> list[tuple[str, str]]:
    """Flatten ``MODEL_OPTIONS`` to ``(provider, model)`` pairs,
    excluding the "custom" sentinel that users type by hand."""
    pairs: list[tuple[str, str]] = []
    for provider, modes in MODEL_OPTIONS.items():
        for mode_options in modes.values():
            for _label, value in mode_options:
                if value == "custom":
                    continue
                pairs.append((provider, value))
    return pairs


@pytest.mark.parametrize("provider,model", _catalog_models())
def test_every_catalog_model_has_a_price(provider: str, model: str):
    """Every model exposed in the CLI dropdown must have a price.

    If you add a model to ``model_catalog``, this test fails until you
    also add it to ``pricing.PRICING``. That coupling is intentional:
    a missing entry would silently make the cost estimate read $0
    for that model in mixed-provider runs.
    """
    price = get_price(provider, model)
    assert price is not None, (
        f"Model {model!r} in provider {provider!r} is in the CLI catalog "
        f"but not in pricing.PRICING. Add it to tradingagents/llm_clients/pricing.py."
    )
    in_rate, out_rate = price
    assert in_rate >= 0 and out_rate >= 0
    assert (in_rate, out_rate) != (0.0, 0.0) or provider in (
        "agnes", "ollama", "sensenova",
    ), (
        f"Model {model!r} under {provider!r} is priced at $0/$0 — only "
        f"Agnes AI, Ollama, and SenseNova (during the public-beta Token "
        f"Plan) should be free. If the model is genuinely free, document "
        f"the free tier in the catalog comment and add the provider to "
        f"this whitelist."
    )


# ---- Specific price pins --------------------------------------------------


def test_agnes_is_free():
    """The whole point of surfacing Agnes AI is the 0-cost tier."""
    assert get_price("agnes", "agnes-2.0-flash") == (0.00, 0.00)


def test_ollama_is_free():
    """Ollama runs locally, so API cost is zero regardless of model size."""
    for model in ("qwen3:latest", "gpt-oss:latest", "glm-4.7-flash:latest"):
        assert get_price("ollama", model) == (0.00, 0.00)


def test_sensenova_flash_lite_is_free_during_beta():
    """SenseNova 6.7 Flash-Lite is in the public-beta Token Plan
    (¥0/month, 1,500 calls/5h, verified 2026-06). When SenseTime
    publishes the post-beta rate, this test is the single place
    to update alongside the PRICING dict entry."""
    assert get_price("sensenova", "sensenova-6.7-flash-lite") == (0.00, 0.00)


def test_deepseek_pricing_matches_published_rates():
    """DeepSeek's published V4-Flash rate is $0.14/$0.28 per 1M
    (cache-miss input / output, verified 2026-06). The V3 chat
    baseline is $0.27/$1.10 — the two must not be confused."""
    assert get_price("deepseek", "deepseek-v4-flash") == (0.14, 0.28)
    assert get_price("deepseek", "deepseek-chat") == (0.27, 1.10)


def test_qwen_cn_and_global_share_pricing():
    """qwen and qwen-cn should expose identical rates (same model IDs)."""
    for model in get_price_for_model.__globals__["PRICING"]["qwen"]:
        assert get_price("qwen", model) == get_price("qwen-cn", model)


def test_minimax_cn_and_global_share_pricing():
    """minimax and minimax-cn should expose identical rates."""
    for model in PRICING["minimax"]:
        assert get_price("minimax", model) == get_price("minimax-cn", model)


# ---- Provider-agnostic lookup (used by callback) -------------------------


def test_get_price_for_model_finds_known_model():
    """Spot-check the local catalog for two well-known rates.
    The 2026-06 OpenAI GPT-5.4 rate is $2.50/$15.00 (long-context
    >272K tier charges more, but TradingAgents prompts fit in the
    short tier)."""
    assert get_price_for_model("gpt-5.4") == (2.50, 15.00)
    assert get_price_for_model("deepseek-v4-flash") == (0.14, 0.28)


def test_get_price_for_model_returns_none_for_unknown():
    assert get_price_for_model("totally-fake-model") is None
    assert get_price_for_model("custom") is None


def test_get_price_for_model_uses_first_match_for_ambiguous_models():
    """``deepseek-v4-flash`` appears under both deepseek and sensenova.
    The catalog iteration order is the source of truth — whatever rate
    is listed first wins. Pin it so a re-order accidentally doesn't
    change the displayed cost."""
    assert get_price_for_model("deepseek-v4-flash") == get_price(
        "deepseek", "deepseek-v4-flash"
    )


def test_get_price_returns_none_for_unknown_provider():
    """The provider itself must be in the catalog for the precise
    lookup. Provider-agnostic ``get_price_for_model`` is the fallback
    the callback uses."""
    assert get_price("not-a-real-provider", "gpt-5.4") is None


# ---- Env-var fallback ----------------------------------------------------


def test_parse_price_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("INPUT_TOKEN_PRICE_PER_1M", raising=False)
    assert _parse_price("INPUT_TOKEN_PRICE_PER_1M") is None


def test_parse_price_returns_float_when_set(monkeypatch):
    monkeypatch.setenv("INPUT_TOKEN_PRICE_PER_1M", "2.5")
    assert _parse_price("INPUT_TOKEN_PRICE_PER_1M") == 2.5


def test_parse_price_returns_none_for_garbage(monkeypatch):
    monkeypatch.setenv("INPUT_TOKEN_PRICE_PER_1M", "not-a-number")
    assert _parse_price("INPUT_TOKEN_PRICE_PER_1M") is None


# ---- _extract_model_name --------------------------------------------------


def test_extract_model_name_from_openai_serialized():
    serialized = {"kwargs": {"model_name": "gpt-5.4", "temperature": 0.0}}
    assert _extract_model_name(serialized) == "gpt-5.4"


def test_extract_model_name_from_anthropic_serialized():
    """Anthropic's integration uses ``model`` instead of ``model_name``."""
    serialized = {"kwargs": {"model": "claude-opus-4-8"}}
    assert _extract_model_name(serialized) == "claude-opus-4-8"


def test_extract_model_name_prefers_model_name_over_model():
    """If both are present, ``model_name`` wins (it's the more common
    convention). The fallback to ``model`` only exists for the
    Anthropic-integration quirk."""
    serialized = {"kwargs": {"model_name": "gpt-5.4", "model": "stale"}}
    assert _extract_model_name(serialized) == "gpt-5.4"


def test_extract_model_name_returns_none_for_empty_serialized():
    assert _extract_model_name({}) is None
    assert _extract_model_name(None) is None
    assert _extract_model_name("not-a-dict") is None


# ---- StatsCallbackHandler end-to-end --------------------------------------


def _make_chat_result(model_name: str, in_tokens: int, out_tokens: int) -> LLMResult:
    """Build a minimal LangChain LLMResult that the callback can parse."""
    msg = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": in_tokens + out_tokens,
        },
    )
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


def test_callback_prices_catalogue_model():
    """A 1M-token call against a catalog model must use the catalog rate."""
    handler = StatsCallbackHandler()
    handler.on_chat_model_start(
        serialized={"kwargs": {"model_name": "deepseek-v4-flash"}},
        messages=[],
    )
    handler.on_llm_end(_make_chat_result("deepseek-v4-flash", 1_000_000, 0))
    stats = handler.get_stats()
    # 1M in tokens × $0.14 (V4-Flash cache-miss input rate) = $0.14
    assert stats["cost"] == pytest.approx(0.14)
    assert stats["cost_by_model"] == {"deepseek-v4-flash": pytest.approx(0.14)}


def test_callback_prices_multiple_models_independently():
    """Mixed-provider run: each model gets its own bucket, the rolled-up
    ``cost`` is the sum. This is the headline improvement over the
    pre-catalog env-var-only behavior."""
    handler = StatsCallbackHandler()
    # DeepSeek V4-Flash: 1M in, 0 out → $0.14
    handler.on_chat_model_start(
        serialized={"kwargs": {"model_name": "deepseek-v4-flash"}},
        messages=[],
    )
    handler.on_llm_end(_make_chat_result("deepseek-v4-flash", 1_000_000, 0))
    # OpenAI gpt-5.4: 1M in, 0 out → $2.50
    handler.on_chat_model_start(
        serialized={"kwargs": {"model_name": "gpt-5.4"}},
        messages=[],
    )
    handler.on_llm_end(_make_chat_result("gpt-5.4", 1_000_000, 0))
    # Agnes: free
    handler.on_chat_model_start(
        serialized={"kwargs": {"model_name": "agnes-2.0-flash"}},
        messages=[],
    )
    handler.on_llm_end(_make_chat_result("agnes-2.0-flash", 1_000_000, 1_000_000))

    stats = handler.get_stats()
    assert stats["cost_by_model"] == {
        "deepseek-v4-flash": pytest.approx(0.14),
        "gpt-5.4":            pytest.approx(2.50),
        "agnes-2.0-flash":    pytest.approx(0.00),
    }
    assert stats["cost"] == pytest.approx(2.64)
    # Token buckets: 1M in + 1M in + 2M in for input, 0 + 0 + 1M for output.
    assert stats["tokens_in"] == 3_000_000
    assert stats["tokens_out"] == 1_000_000
    assert stats["tokens_by_model"]["deepseek-v4-flash"] == {
        "in": 1_000_000, "out": 0,
    }


def test_callback_falls_back_to_env_var_for_unknown_model(monkeypatch):
    """When a model isn't in the catalog, env-var defaults take over —
    matches the pre-catalog behavior so users who relied on the env
    var don't see a regression."""
    monkeypatch.setenv("INPUT_TOKEN_PRICE_PER_1M", "1.00")
    monkeypatch.setenv("OUTPUT_TOKEN_PRICE_PER_1M", "3.00")
    handler = StatsCallbackHandler()
    handler.on_chat_model_start(
        serialized={"kwargs": {"model_name": "not-in-catalog"}},
        messages=[],
    )
    handler.on_llm_end(_make_chat_result("not-in-catalog", 1_000_000, 1_000_000))
    stats = handler.get_stats()
    # 1M in × $1 + 1M out × $3 = $4
    assert stats["cost"] == pytest.approx(4.00)
    assert stats["cost_by_model"] == {"not-in-catalog": pytest.approx(4.00)}


def test_callback_returns_none_cost_when_no_pricing_available(monkeypatch):
    """If neither catalog nor env-var has the model, the cost is None
    and the per-model bucket is absent — the dashboard must show
    'Cost: --' rather than 'Cost: $0.00' (which would lie)."""
    monkeypatch.delenv("INPUT_TOKEN_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("OUTPUT_TOKEN_PRICE_PER_1M", raising=False)
    handler = StatsCallbackHandler()
    handler.on_chat_model_start(
        serialized={"kwargs": {"model_name": "not-in-catalog"}},
        messages=[],
    )
    handler.on_llm_end(_make_chat_result("not-in-catalog", 1_000_000, 0))
    stats = handler.get_stats()
    assert stats["cost"] is None
    assert stats["cost_by_model"] == {}


def test_callback_preserves_legacy_zero_cost_for_agnes():
    """Agnes is in the catalog at $0/$0, so a 1M-token call costs
    exactly $0.00 (preserved through the per-model bucket)."""
    handler = StatsCallbackHandler()
    handler.on_chat_model_start(
        serialized={"kwargs": {"model_name": "agnes-2.0-flash"}},
        messages=[],
    )
    handler.on_llm_end(_make_chat_result("agnes-2.0-flash", 1_000_000, 1_000_000))
    stats = handler.get_stats()
    assert stats["cost"] == pytest.approx(0.00)
    assert stats["cost_by_model"]["agnes-2.0-flash"] == pytest.approx(0.00)


def test_callback_uses_default_unknown_bucket_when_model_name_missing(monkeypatch):
    """When the LangChain serialized dict doesn't expose a model name
    (older integrations), usage still rolls up under the ``"unknown"``
    bucket so the token counts don't disappear."""
    # Strip the env-var defaults the user's .env may set so the
    # "no pricing available" branch is actually exercised.
    monkeypatch.delenv("INPUT_TOKEN_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("OUTPUT_TOKEN_PRICE_PER_1M", raising=False)
    handler = StatsCallbackHandler()
    # on_chat_model_start with empty kwargs → model_name is None
    handler.on_chat_model_start(serialized={"kwargs": {}}, messages=[])
    handler.on_llm_end(_make_chat_result("unknown", 100, 50))
    stats = handler.get_stats()
    assert stats["tokens_by_model"] == {"unknown": {"in": 100, "out": 50}}
    # Cost is None because the model isn't in the catalog and we
    # didn't set env-var defaults in this test.
    assert stats["cost"] is None


# ---- LiteLLM overlay -----------------------------------------------------


def _litellm_payload(models: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal but valid LiteLLM-format payload for testing."""
    return {
        "sample_spec": {"input_cost_per_token": 0},  # skipped
        **{
            name: {
                "input_cost_per_token":  rates["in"] / 1_000_000,
                "output_cost_per_token": rates["out"] / 1_000_000,
                "litellm_provider":      rates.get("provider", "openai"),
            }
            for name, rates in models.items()
        },
    }


def test_litellm_overlay_loads_from_disk_cache(tmp_path, monkeypatch):
    """A fresh disk cache is honored without hitting the network."""
    cache_path = tmp_path / "litellm_pricing.json"
    cache_path.write_text(json.dumps(_litellm_payload({
        "gpt-5.4":       {"in": 2.50, "out": 15.00, "provider": "openai"},
        "claude-opus-4-8": {"in": 5.00, "out": 25.00, "provider": "anthropic"},
    })))
    monkeypatch.setattr(pricing, "_LITELLM_CACHE_PATH", str(cache_path))

    overlay = _load_litellm_overlay()
    assert overlay["gpt-5.4"] == (2.50, 15.00)
    assert overlay["claude-opus-4-8"] == (5.00, 25.00)
    assert "sample_spec" not in overlay


def test_litellm_overlay_falls_back_when_cache_missing_and_network_fails(
    tmp_path, monkeypatch,
):
    """No cache + no network → empty overlay, no exception raised.
    The caller will silently fall through to the local PRICING dict."""
    monkeypatch.setattr(pricing, "_LITELLM_CACHE_PATH", str(tmp_path / "missing.json"))
    with patch("httpx.get", side_effect=RuntimeError("network down")):
        overlay = _load_litellm_overlay()
    assert overlay == {}


def test_litellm_overlay_fetches_from_network_when_cache_stale(
    tmp_path, monkeypatch,
):
    """A cache older than 24h is ignored and replaced with a fresh fetch."""
    cache_path = tmp_path / "litellm_pricing.json"
    cache_path.write_text(json.dumps(_litellm_payload({
        "stale-model": {"in": 999, "out": 999, "provider": "openai"},
    })))
    # Force the cache to look stale by backdating mtime.
    import time
    old_time = time.time() - pricing._LITELLM_TTL_SECONDS - 60
    os.utime(cache_path, (old_time, old_time))
    monkeypatch.setattr(pricing, "_LITELLM_CACHE_PATH", str(cache_path))

    fresh_payload = _litellm_payload({
        "gpt-5.4": {"in": 2.50, "out": 15.00, "provider": "openai"},
    })
    with patch("httpx.get") as mock_get:
        mock_get.return_value.json.return_value = fresh_payload
        mock_get.return_value.raise_for_status = lambda: None
        overlay = _load_litellm_overlay()
    assert "gpt-5.4" in overlay
    assert "stale-model" not in overlay  # cache was bypassed


def test_litellm_overlay_rejects_shrunken_payload(tmp_path, monkeypatch):
    """If the fetched payload has <50% of the cached model count, treat
    it as corrupt and fall through to the local catalog. The integrity
    check mirrors LiteLLM's own ``_check_model_count_not_reduced`` rule.

    The cache must be backdated to look stale so the fetch path
    actually runs; otherwise the cache-1) early-return would just
    hand back the healthy cache without consulting the network."""
    import time

    cache_path = tmp_path / "litellm_pricing.json"
    # Seed a big cache (1000 models) so any shrinkage trips the check.
    big = _litellm_payload({
        f"model-{i}": {"in": 1.0, "out": 2.0, "provider": "openai"}
        for i in range(1000)
    })
    cache_path.write_text(json.dumps(big))
    # Backdate so the fetch path runs.
    old_time = time.time() - pricing._LITELLM_TTL_SECONDS - 60
    os.utime(cache_path, (old_time, old_time))
    monkeypatch.setattr(pricing, "_LITELLM_CACHE_PATH", str(cache_path))

    # Fetch returns only 10 models — well below the 50% threshold
    # (10 < 1000 * 0.5 = 500).
    tiny = _litellm_payload({
        f"tiny-{i}": {"in": 1.0, "out": 2.0, "provider": "openai"}
        for i in range(10)
    })
    with patch("httpx.get") as mock_get:
        mock_get.return_value.json.return_value = tiny
        mock_get.return_value.raise_for_status = lambda: None
        overlay = _load_litellm_overlay()
    # Empty overlay — the local PRICING dict takes over.
    assert overlay == {}


def test_litellm_overlay_skips_deprecated_models():
    """Models with a past ``deprecation_date`` are dropped from the
    overlay even if their entry is otherwise well-formed."""
    import datetime as _dt
    today = _dt.date.today()
    past = (today - _dt.timedelta(days=30)).isoformat()
    payload = {
        "live-model": {
            "input_cost_per_token":  1e-6,
            "output_cost_per_token": 2e-6,
            "litellm_provider":      "openai",
        },
        "old-model": {
            "input_cost_per_token":  1e-6,
            "output_cost_per_token": 2e-6,
            "litellm_provider":      "openai",
            "deprecation_date":      past,
        },
    }
    overlay = _parse_litellm_payload(payload)
    assert "live-model" in overlay
    assert "old-model" not in overlay


def test_litellm_overlay_converts_per_token_to_per_million():
    """LiteLLM stores per-token rates; the overlay must be per-million
    so the callback can use ``tokens / 1M * rate`` directly."""
    overlay = _parse_litellm_payload({
        "x": {
            "input_cost_per_token":  5e-6,   # $5 per 1M
            "output_cost_per_token": 2e-5,   # $20 per 1M
            "litellm_provider":      "openai",
        },
    })
    assert overlay["x"] == (5.0, 20.0)


def test_local_catalog_used_when_litellm_omits_provider(tmp_path, monkeypatch):
    """End-to-end: when LiteLLM doesn't carry a Chinese provider's
    model, ``get_price_for_model`` falls through to the local
    ``PRICING`` dict (which is the primary source for these)."""
    # Force the overlay to be empty so we test the local-PRICING path.
    cache_path = tmp_path / "litellm_pricing.json"
    cache_path.write_text(json.dumps({}))
    monkeypatch.setattr(pricing, "_LITELLM_CACHE_PATH", str(cache_path))

    # Local-only entries must still resolve.
    assert get_price_for_model("deepseek-v4-flash") == (0.14, 0.28)
    assert get_price_for_model("agnes-2.0-flash") == (0.00, 0.00)
    assert get_price_for_model("qwen3.7-max") == (2.50, 7.50)


# =========================================================================
# Edge-case tests merged from test_remaining_coverage.py
# =========================================================================


class PricingCorruptCacheTests(_TempDirMixin, unittest.TestCase):
    """Lines 296-297: corrupt fresh cache falls through to network."""

    def test_corrupt_fresh_cache_falls_to_network(self):
        cache_file = self._tmp / "litellm_pricing.json"
        cache_file.write_text("{bad json}!", encoding="utf-8")
        with patch.object(pricing, "_LITELLM_CACHE_PATH", str(cache_file)):
            fresh = _litellm_payload({"gpt-5.4": {"in": 2.50, "out": 15.00}})
            with patch("httpx.get") as mock_get:
                mock_get.return_value.json.return_value = fresh
                mock_get.return_value.raise_for_status = lambda: None
                overlay = _load_litellm_overlay()
        self.assertIn("gpt-5.4", overlay)

    def test_network_fails_stale_cache_corrupt(self):
        """Lines 313-317: network fails, stale cache is bad JSON -> {}."""
        cache_file = self._tmp / "litellm_pricing.json"
        cache_file.write_text("{bad json}!", encoding="utf-8")
        old = time.time() - pricing._LITELLM_TTL_SECONDS - 60
        os.utime(cache_file, (old, old))
        with patch.object(pricing, "_LITELLM_CACHE_PATH", str(cache_file)):
            with patch("httpx.get", side_effect=RuntimeError("network down")):
                overlay = _load_litellm_overlay()
        self.assertEqual(overlay, {})

    def test_network_fails_stale_cache_valid(self):
        """Line 315: network fails, stale cache has valid JSON -> parsed result."""
        cache_file = self._tmp / "litellm_pricing.json"
        stale_data = _litellm_payload({"gpt-5.4": {"in": 2.50, "out": 15.00}})
        cache_file.write_text(json.dumps(stale_data), encoding="utf-8")
        old = time.time() - pricing._LITELLM_TTL_SECONDS - 60
        os.utime(cache_file, (old, old))
        with patch.object(pricing, "_LITELLM_CACHE_PATH", str(cache_file)):
            with patch("httpx.get", side_effect=RuntimeError("network down")):
                overlay = _load_litellm_overlay()
        self.assertEqual(overlay["gpt-5.4"], (2.50, 15.00))


class PricingIntegrityCheckTests(_TempDirMixin, unittest.TestCase):
    """Lines 328, 333-336: integrity check edge cases."""

    def test_rejects_non_dict_payload(self):
        """Line 328: fetched data is not a dict -> {}."""
        cache_file = self._tmp / "litellm_pricing.json"
        cache_file.write_text("{}", encoding="utf-8")
        old = time.time() - pricing._LITELLM_TTL_SECONDS - 60
        os.utime(cache_file, (old, old))
        with patch.object(pricing, "_LITELLM_CACHE_PATH", str(cache_file)):
            with patch("httpx.get") as mock_get:
                mock_get.return_value.json.return_value = ["not", "a", "dict"]
                mock_get.return_value.raise_for_status = lambda: None
                overlay = _load_litellm_overlay()
        self.assertEqual(overlay, {})

    def test_integrity_check_with_corrupt_backup(self):
        """Lines 333-334: backup read fails -> backup_count=0, check passes."""
        cache_file = self._tmp / "litellm_pricing.json"
        cache_file.write_text("garbage content", encoding="utf-8")
        old = time.time() - pricing._LITELLM_TTL_SECONDS - 60
        os.utime(cache_file, (old, old))
        with patch.object(pricing, "_LITELLM_CACHE_PATH", str(cache_file)):
            fresh = _litellm_payload({"gpt-5.4": {"in": 2.50, "out": 15.00}})
            with patch("httpx.get") as mock_get:
                mock_get.return_value.json.return_value = fresh
                mock_get.return_value.raise_for_status = lambda: None
                overlay = _load_litellm_overlay()
        self.assertIn("gpt-5.4", overlay)

    def test_integrity_check_no_backup(self):
        """Lines 335-336: cache deleted before backup check -> backup_count=0."""
        cache_file = self._tmp / "litellm_pricing.json"
        cache_file.write_text(json.dumps({"old": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6}}), encoding="utf-8")
        old = time.time() - pricing._LITELLM_TTL_SECONDS - 60
        os.utime(cache_file, (old, old))

        def delete_and_raise(*args, **kwargs):
            if cache_file.exists():
                cache_file.unlink()
            raise RuntimeError("simulated")

        with patch.object(pricing, "_LITELLM_CACHE_PATH", str(cache_file)):
            with patch("httpx.get", side_effect=delete_and_raise):
                overlay = _load_litellm_overlay()
        self.assertEqual(overlay, {})


class PricingWriteFailureTests(_TempDirMixin, unittest.TestCase):
    """Line 348-349: OSError on cache write is silently ignored."""

    def test_write_failure_returns_parsed_result(self):
        cache_file = self._tmp / "litellm_pricing.json"
        with patch.object(pricing, "_LITELLM_CACHE_PATH", str(cache_file)):
            fresh = _litellm_payload({"gpt-5.4": {"in": 2.50, "out": 15.00}})
            with patch("httpx.get") as mock_get:
                mock_get.return_value.json.return_value = fresh
                mock_get.return_value.raise_for_status = lambda: None
                with patch.object(Path, "write_text", side_effect=OSError("read-only")):
                    overlay = _load_litellm_overlay()
        self.assertIn("gpt-5.4", overlay)


class PricingParseEdgeCases(unittest.TestCase):
    """_parse_litellm_payload edge cases: lines 369, 379-380, 387-388, 390."""

    def test_skips_non_dict_entry(self):
        payload = {
            "valid-model": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6},
            "bad-entry": "not a dict",
        }
        result = _parse_litellm_payload(payload)
        self.assertIn("valid-model", result)
        self.assertNotIn("bad-entry", result)

    def test_skips_bad_deprecation_date(self):
        payload = {
            "good": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6},
            "bad-dep": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6,
                        "deprecation_date": "not-a-date"},
            "int-dep": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6,
                        "deprecation_date": 12345},
        }
        result = _parse_litellm_payload(payload)
        self.assertIn("good", result)
        self.assertIn("bad-dep", result)
        self.assertIn("int-dep", result)

    def test_skips_unparseable_cost(self):
        payload = {
            "bad-input": {"input_cost_per_token": "not_a_number", "output_cost_per_token": 2e-6},
            "bad-output": {"input_cost_per_token": 1e-6, "output_cost_per_token": [1, 2, 3]},
            "good": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6},
        }
        result = _parse_litellm_payload(payload)
        self.assertIn("good", result)
        self.assertNotIn("bad-input", result)
        self.assertNotIn("bad-output", result)

    def test_skips_negative_cost(self):
        payload = {
            "neg-input": {"input_cost_per_token": -1e-6, "output_cost_per_token": 2e-6},
            "neg-output": {"input_cost_per_token": 1e-6, "output_cost_per_token": -2e-6},
            "good": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6},
        }
        result = _parse_litellm_payload(payload)
        self.assertIn("good", result)
        self.assertNotIn("neg-input", result)
        self.assertNotIn("neg-output", result)
