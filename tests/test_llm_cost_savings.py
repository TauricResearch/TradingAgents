"""Prompt caching on Anthropic tool loops, the analyst report word budget, and
cache-aware cost metering in decide.py."""

import importlib.util
import sys
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from tradingagents.agents.context import get_report_length_instruction
from tradingagents.dataflows import config as df_config
from tradingagents.default_config import DEFAULT_CONFIG, build_default_config
from tradingagents.llm_clients import anthropic_client as mod
from tradingagents.llm_clients.factory import build_llm_kwargs, create_llm_client


@tool
def get_price(ticker: str) -> str:
    """Price for a ticker."""
    return "100"


_MSGS = [SystemMessage(content="system prompt"), HumanMessage(content="analyse WIPRO")]


def _llm(cache: bool):
    return mod.NormalizedChatAnthropic(model="claude-haiku-4-5", api_key="x", cache_tool_loops=cache)


def _payload(llm, **kwargs):
    return llm._get_request_payload(_MSGS, **kwargs)


@pytest.mark.unit
class TestPromptCache:
    def test_tool_bound_call_gets_top_level_cache_control(self):
        bound = _llm(True).bind_tools([get_price])
        payload = _payload(bound.bound, **bound.kwargs)
        assert payload["cache_control"] == {"type": "ephemeral"}

    def test_single_shot_call_is_not_cached(self):
        assert "cache_control" not in _payload(_llm(True))

    def test_flag_off_never_caches(self):
        bound = _llm(False).bind_tools([get_price])
        assert "cache_control" not in _payload(bound.bound, **bound.kwargs)

    def test_explicit_cache_control_is_not_overridden(self):
        bound = _llm(True).bind_tools([get_price])
        payload = _payload(bound.bound, **bound.kwargs, cache_control={"type": "ephemeral", "ttl": "1h"})
        assert payload["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    def test_factory_wires_flag_for_anthropic_only(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(mod, "NormalizedChatAnthropic", lambda **kw: captured.update(kw))
        kwargs = build_llm_kwargs({**DEFAULT_CONFIG, "llm_provider": "anthropic"})
        create_llm_client("anthropic", "claude-haiku-4-5", api_key="x", **kwargs).get_llm()
        assert captured["cache_tool_loops"] is True
        assert "cache_tool_loops" not in build_llm_kwargs({**DEFAULT_CONFIG, "llm_provider": "deepseek"})

    def test_env_can_turn_caching_off(self, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_ANTHROPIC_PROMPT_CACHE", "false")
        assert build_default_config()["anthropic_prompt_cache"] is False


@pytest.mark.unit
class TestReportWordBudget:
    def test_default_is_off(self):
        assert DEFAULT_CONFIG["report_word_budget"] == 0
        df_config.set_config({"report_word_budget": 0})
        assert get_report_length_instruction() == ""

    def test_budget_produces_instruction(self):
        df_config.set_config({"report_word_budget": 400})
        try:
            text = get_report_length_instruction()
        finally:
            df_config.set_config({"report_word_budget": 0})
        assert "under 400 words" in text

    def test_env_override_is_an_int(self, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_REPORT_WORD_BUDGET", "350")
        assert build_default_config()["report_word_budget"] == 350


def _decide():
    path = Path(__file__).parent.parent / "scripts" / "decide.py"
    spec = importlib.util.spec_from_file_location("decide_cost_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["decide_cost_under_test"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
class TestCacheAwareCost:
    def test_uncached_usage_unchanged(self):
        cost, unpriced = _decide()._compute_cost(
            {"claude-haiku-4-5": {"input_tokens": 1_000_000, "output_tokens": 100_000}})
        assert unpriced == []
        assert cost == pytest.approx(1.00 + 0.50)

    def test_cache_reads_and_writes_are_priced_separately(self):
        usage = {"claude-haiku-4-5-20251001": {
            "input_tokens": 1_000_000, "output_tokens": 0,
            "input_token_details": {"cache_read": 600_000, "cache_creation": 200_000}}}
        cost, _ = _decide()._compute_cost(usage)
        assert cost == pytest.approx((200_000 + 0.1 * 600_000 + 1.25 * 200_000) / 1_000_000 * 1.00)
