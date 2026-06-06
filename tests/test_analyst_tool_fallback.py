"""Tests for the tool-free analyst fallback used by chat-only providers.

The market, news, and fundamentals analysts normally call ``bind_tools``
so the model drives a tool-use loop. Chat-only providers (codex) raise
``NotImplementedError`` from ``bind_tools``; these analysts must then
pre-fetch the same data deterministically and inject it into the prompt
instead of crashing.

Covers:
  * the shared ``bind_tools_or_none`` / ``safe_tool_text`` helpers
  * each analyst's tool-free path (data pre-fetched + injected, llm.invoke used)
  * the market analyst's normal tool path still works after the refactor
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from tradingagents.agents.analysts import (
    fundamentals_analyst as fund_mod,
    market_analyst as market_mod,
    news_analyst as news_mod,
)
from tradingagents.agents.utils.tool_fallback import bind_tools_or_none, safe_tool_text


# ---------------------------------------------------------------------------
# bind_tools_or_none
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBindToolsOrNone:
    def test_returns_bound_when_supported(self):
        llm = MagicMock()
        llm.bind_tools.return_value = "BOUND"
        assert bind_tools_or_none(llm, [], "X") == "BOUND"

    def test_returns_none_on_not_implemented(self, caplog):
        llm = MagicMock()
        llm.bind_tools.side_effect = NotImplementedError("codex runs its own loop")
        assert bind_tools_or_none(llm, [], "Market Analyst") is None
        assert any("does not support bind_tools" in r.getMessage() for r in caplog.records)

    def test_returns_none_on_attribute_error(self):
        llm = MagicMock()
        llm.bind_tools.side_effect = AttributeError("no bind_tools")
        assert bind_tools_or_none(llm, [], "X") is None


# ---------------------------------------------------------------------------
# safe_tool_text
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSafeToolText:
    def test_returns_text(self):
        assert safe_tool_text("snapshot", lambda: "DATA") == "DATA"

    def test_exception_becomes_placeholder(self):
        out = safe_tool_text("snapshot", lambda: (_ for _ in ()).throw(ValueError("boom")))
        assert out == "<snapshot unavailable: boom>"

    def test_empty_becomes_placeholder(self):
        assert safe_tool_text("snapshot", lambda: "   ") == "<snapshot unavailable: empty result>"
        assert safe_tool_text("snapshot", lambda: None) == "<snapshot unavailable: empty result>"


# ---------------------------------------------------------------------------
# Analyst tool-free fallbacks
# ---------------------------------------------------------------------------


def _tool_free_llm(report: str):
    """LLM whose bind_tools refuses (like codex) and whose invoke returns report."""
    llm = MagicMock()
    llm.bind_tools.side_effect = NotImplementedError("codex runs its own tool loop")
    llm.invoke.return_value = AIMessage(content=report)
    return llm


def _system_text(call_args):
    """Concatenate the content of every message llm.invoke was called with."""
    messages = call_args[0][0]
    return "\n".join(str(m.content) for m in messages)


@pytest.mark.unit
class TestMarketAnalystToolFree:
    def test_prefetches_data_and_injects_into_prompt(self, monkeypatch):
        monkeypatch.setattr(
            market_mod, "get_verified_market_snapshot",
            SimpleNamespace(func=lambda *a, **k: "SNAPSHOT_SENTINEL"),
        )
        monkeypatch.setattr(
            market_mod, "get_stock_data",
            SimpleNamespace(func=lambda *a, **k: "OHLCV_SENTINEL"),
        )
        monkeypatch.setattr(
            market_mod, "get_indicators",
            SimpleNamespace(func=lambda *a, **k: "INDICATORS_SENTINEL"),
        )
        llm = _tool_free_llm("MARKET_REPORT")
        node = market_mod.create_market_analyst(llm)

        result = node({"trade_date": "2026-01-15", "company_of_interest": "NVDA", "messages": []})

        assert result["market_report"] == "MARKET_REPORT"
        assert result["messages"][0].content == "MARKET_REPORT"
        llm.invoke.assert_called_once()
        injected = _system_text(llm.invoke.call_args)
        assert "SNAPSHOT_SENTINEL" in injected
        assert "OHLCV_SENTINEL" in injected
        assert "INDICATORS_SENTINEL" in injected
        # Codex must never be handed the report-killing empty path: a tool-free
        # report is the model's content, not "".
        assert result["market_report"] != ""

    def test_tool_path_still_used_when_bind_tools_supported(self):
        llm = MagicMock()
        llm.bind_tools.return_value = lambda _prompt_value: AIMessage(content="TOOLPATH_REPORT")
        node = market_mod.create_market_analyst(llm)

        result = node({"trade_date": "2026-01-15", "company_of_interest": "NVDA", "messages": []})

        assert result["market_report"] == "TOOLPATH_REPORT"
        llm.bind_tools.assert_called_once()
        llm.invoke.assert_not_called()  # the bound chain handled it, not free-text


@pytest.mark.unit
class TestNewsAnalystToolFree:
    def test_prefetches_news_and_injects_into_prompt(self, monkeypatch):
        monkeypatch.setattr(
            news_mod, "get_news",
            SimpleNamespace(func=lambda *a, **k: "COMPANY_NEWS_SENTINEL"),
        )
        monkeypatch.setattr(
            news_mod, "get_global_news",
            SimpleNamespace(func=lambda *a, **k: "GLOBAL_NEWS_SENTINEL"),
        )
        llm = _tool_free_llm("NEWS_REPORT")
        node = news_mod.create_news_analyst(llm)

        result = node({"trade_date": "2026-01-15", "company_of_interest": "NVDA", "messages": []})

        assert result["news_report"] == "NEWS_REPORT"
        injected = _system_text(llm.invoke.call_args)
        assert "COMPANY_NEWS_SENTINEL" in injected
        assert "GLOBAL_NEWS_SENTINEL" in injected


@pytest.mark.unit
class TestFundamentalsAnalystToolFree:
    def test_prefetches_statements_and_injects_into_prompt(self, monkeypatch):
        monkeypatch.setattr(
            fund_mod, "get_fundamentals",
            SimpleNamespace(func=lambda *a, **k: "FUNDAMENTALS_SENTINEL"),
        )
        monkeypatch.setattr(
            fund_mod, "get_balance_sheet",
            SimpleNamespace(func=lambda *a, **k: "BALANCE_SENTINEL"),
        )
        monkeypatch.setattr(
            fund_mod, "get_cashflow",
            SimpleNamespace(func=lambda *a, **k: "CASHFLOW_SENTINEL"),
        )
        monkeypatch.setattr(
            fund_mod, "get_income_statement",
            SimpleNamespace(func=lambda *a, **k: "INCOME_SENTINEL"),
        )
        llm = _tool_free_llm("FUNDAMENTALS_REPORT")
        node = fund_mod.create_fundamentals_analyst(llm)

        result = node({"trade_date": "2026-01-15", "company_of_interest": "NVDA", "messages": []})

        assert result["fundamentals_report"] == "FUNDAMENTALS_REPORT"
        injected = _system_text(llm.invoke.call_args)
        assert "FUNDAMENTALS_SENTINEL" in injected
        assert "BALANCE_SENTINEL" in injected
        assert "CASHFLOW_SENTINEL" in injected
        assert "INCOME_SENTINEL" in injected
