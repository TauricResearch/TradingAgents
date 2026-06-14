"""The run manifest records model/provider, key-presence (booleans only), data
coverage, analysts, and usage — and never leaks secret values."""

from __future__ import annotations

import copy

import pytest

import tradingagents.default_config as default_config
from tradingagents.config_validation import validate_config
from tradingagents.manifest import build_manifest
from tradingagents.usage import UsageTrackingCallback


def _config(**overrides):
    cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
    cfg["llm_provider"] = "openrouter"
    cfg["deep_think_llm"] = "minimax/minimax-m2.7"
    cfg["quick_think_llm"] = "minimax/minimax-m2.7"
    cfg.update(overrides)
    return cfg


@pytest.mark.unit
def test_manifest_core_fields():
    env = {"OPENROUTER_API_KEY": "secret-value", "FRED_API_KEY": "another-secret"}
    m = build_manifest(_config(), "NVDA", "2026-06-12", ["market", "news"], env=env)

    assert m["ticker"] == "NVDA"
    assert m["trade_date"] == "2026-06-12"
    assert m["selected_analysts"] == ["market", "news"]
    assert m["llm"]["provider"] == "openrouter"
    assert m["llm"]["deep_think_llm"] == "minimax/minimax-m2.7"
    assert "data_vendors" in m


@pytest.mark.unit
def test_manifest_records_presence_not_values():
    env = {"OPENROUTER_API_KEY": "sk-or-SECRET", "FRED_API_KEY": ""}
    m = build_manifest(_config(), "NVDA", "2026-06-12", ["news"], env=env)

    present = m["api_keys_present"]
    assert present["OPENROUTER_API_KEY"] is True   # set
    assert present["FRED_API_KEY"] is False        # empty
    assert present["ALPHA_VANTAGE_API_KEY"] is False  # absent

    # Crucially: no secret value appears anywhere in the manifest.
    blob = repr(m)
    assert "sk-or-SECRET" not in blob
    assert "secret" not in blob.lower() or "secret-value" not in blob


@pytest.mark.unit
def test_manifest_includes_preflight_and_usage():
    env = {"OPENROUTER_API_KEY": "x"}  # no FRED -> macro optional miss
    preflight = validate_config(["news"], _config(), env=env)

    usage = UsageTrackingCallback(model_prices={"input": 0.3, "output": 1.2})
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult
    usage.on_chat_model_start({}, [[]])
    usage.on_llm_end(
        LLMResult(generations=[[ChatGeneration(
            message=AIMessage(content="ok", usage_metadata={
                "input_tokens": 100, "output_tokens": 50, "total_tokens": 150})
        )]])
    )

    m = build_manifest(_config(), "NVDA", "2026-06-12", ["news"],
                       preflight=preflight, usage=usage, env=env)

    assert m["preflight"]["ok"] is True
    assert "macro_data" in m["preflight"]["missing_optional"]
    assert m["usage"]["llm_calls"] == 1
    assert m["usage"]["tokens_total"] == 150
    assert m["usage"]["estimated_cost_usd"] == pytest.approx(100 / 1e6 * 0.3 + 50 / 1e6 * 1.2)
