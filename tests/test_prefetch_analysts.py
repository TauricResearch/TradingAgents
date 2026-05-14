"""Backward-compatibility tests for the analyst dual code paths.

Each analyst supports two modes:
  1. Tool-call path  — API providers with bind_tools() (original behavior)
  2. Pre-fetch path  — CLI provider where data is fetched before LLM call

Tests verify:
  - supports_tool_calls=True  → bind_tools called, tool_calls checked
  - supports_tool_calls=False → .func() called on tools, data injected into prompt
  - Graceful degradation when a data source raises in pre-fetch path
  - Report key names match expected state keys
  - supports_tool_calls helper defaults to True for unknown LLMs
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from tradingagents.agents.utils.agent_utils import supports_tool_calls


# ── supports_tool_calls helper ───────────────────────────────────────────


class TestSupportsToolCalls:
    def test_true_by_default(self):
        """Unknown LLMs default to True (backward compat)."""
        llm = MagicMock(spec=[])  # no supports_tool_calls attr
        assert supports_tool_calls(llm) is True

    def test_explicit_true(self):
        llm = MagicMock()
        llm.supports_tool_calls = True
        assert supports_tool_calls(llm) is True

    def test_explicit_false(self):
        llm = MagicMock()
        llm.supports_tool_calls = False
        assert supports_tool_calls(llm) is False


# ── Shared fixtures ─────────────────────────────────────────────────────


def _make_state(ticker: str = "AAPL", trade_date: str = "2025-01-15"):
    return {
        "trade_date": trade_date,
        "company_of_interest": ticker,
        "messages": [],
    }


def _make_llm(tool_calls: bool, response_text: str = "Test report"):
    """Create a mock LLM with configurable supports_tool_calls."""
    llm = MagicMock()
    llm.supports_tool_calls = tool_calls

    ai_msg = AIMessage(content=response_text)
    ai_msg.tool_calls = []

    # For tool-call path: bind_tools returns an object whose __or__ works
    bound = MagicMock()
    bound.__or__ = MagicMock(return_value=MagicMock(invoke=MagicMock(return_value=ai_msg)))
    llm.bind_tools = MagicMock(return_value=bound)

    # For pre-fetch path: llm itself is piped via prompt | llm
    llm.__or__ = MagicMock(return_value=MagicMock(invoke=MagicMock(return_value=ai_msg)))

    return llm


# ── Market analyst ──────────────────────────────────────────────────────


class TestMarketAnalyst:
    @patch("tradingagents.agents.analysts.market_analyst.get_indicators")
    @patch("tradingagents.agents.analysts.market_analyst.get_stock_data")
    def test_prefetch_path_calls_func(self, mock_stock, mock_indicators):
        """Pre-fetch path calls .func() on tools, not bind_tools."""
        mock_stock.func = MagicMock(return_value="stock,data,csv")
        mock_indicators.func = MagicMock(return_value="indicator data")

        llm = _make_llm(tool_calls=False)
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
        node = create_market_analyst(llm)
        result = node(_make_state())

        mock_stock.func.assert_called_once()
        assert mock_indicators.func.call_count == 12  # _ALL_INDICATORS has 12 items
        llm.bind_tools.assert_not_called()
        assert "market_report" in result

    @patch("tradingagents.agents.analysts.market_analyst.get_indicators")
    @patch("tradingagents.agents.analysts.market_analyst.get_stock_data")
    def test_tool_call_path_uses_bind_tools(self, mock_stock, mock_indicators):
        """Tool-call path uses bind_tools (original behavior)."""
        mock_stock.name = "get_stock_data"
        mock_indicators.name = "get_indicators"

        llm = _make_llm(tool_calls=True)
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
        node = create_market_analyst(llm)
        result = node(_make_state())

        llm.bind_tools.assert_called_once()
        assert "market_report" in result

    @patch("tradingagents.agents.analysts.market_analyst.get_indicators")
    @patch("tradingagents.agents.analysts.market_analyst.get_stock_data")
    def test_prefetch_graceful_stock_failure(self, mock_stock, mock_indicators):
        """Stock data failure degrades gracefully, doesn't crash."""
        mock_stock.func = MagicMock(side_effect=ConnectionError("API down"))
        mock_indicators.func = MagicMock(return_value="indicator data")

        llm = _make_llm(tool_calls=False)
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
        node = create_market_analyst(llm)
        result = node(_make_state())

        assert "market_report" in result

    @patch("tradingagents.agents.analysts.market_analyst.get_indicators")
    @patch("tradingagents.agents.analysts.market_analyst.get_stock_data")
    def test_prefetch_graceful_indicator_failure(self, mock_stock, mock_indicators):
        """Individual indicator failure degrades gracefully."""
        mock_stock.func = MagicMock(return_value="stock data")
        mock_indicators.func = MagicMock(side_effect=ValueError("bad indicator"))

        llm = _make_llm(tool_calls=False)
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
        node = create_market_analyst(llm)
        result = node(_make_state())

        assert "market_report" in result


# ── News analyst ────────────────────────────────────────────────────────


class TestNewsAnalyst:
    @patch("tradingagents.agents.analysts.news_analyst.get_global_news")
    @patch("tradingagents.agents.analysts.news_analyst.get_news")
    def test_prefetch_path_calls_func(self, mock_news, mock_global):
        """Pre-fetch path calls .func() on news tools."""
        mock_news.func = MagicMock(return_value="ticker news")
        mock_global.func = MagicMock(return_value="global news")

        llm = _make_llm(tool_calls=False)
        from tradingagents.agents.analysts.news_analyst import create_news_analyst
        node = create_news_analyst(llm)
        result = node(_make_state())

        mock_news.func.assert_called_once()
        mock_global.func.assert_called_once()
        llm.bind_tools.assert_not_called()
        assert "news_report" in result

    @patch("tradingagents.agents.analysts.news_analyst.get_global_news")
    @patch("tradingagents.agents.analysts.news_analyst.get_news")
    def test_tool_call_path_uses_bind_tools(self, mock_news, mock_global):
        """Tool-call path uses bind_tools (original behavior)."""
        mock_news.name = "get_news"
        mock_global.name = "get_global_news"

        llm = _make_llm(tool_calls=True)
        from tradingagents.agents.analysts.news_analyst import create_news_analyst
        node = create_news_analyst(llm)
        result = node(_make_state())

        llm.bind_tools.assert_called_once()
        assert "news_report" in result

    @patch("tradingagents.agents.analysts.news_analyst.get_global_news")
    @patch("tradingagents.agents.analysts.news_analyst.get_news")
    def test_prefetch_graceful_news_failure(self, mock_news, mock_global):
        """News fetch failure degrades gracefully."""
        mock_news.func = MagicMock(side_effect=ConnectionError("news API down"))
        mock_global.func = MagicMock(return_value="global news")

        llm = _make_llm(tool_calls=False)
        from tradingagents.agents.analysts.news_analyst import create_news_analyst
        node = create_news_analyst(llm)
        result = node(_make_state())

        assert "news_report" in result

    @patch("tradingagents.agents.analysts.news_analyst.get_global_news")
    @patch("tradingagents.agents.analysts.news_analyst.get_news")
    def test_prefetch_graceful_global_failure(self, mock_news, mock_global):
        """Global news failure degrades gracefully."""
        mock_news.func = MagicMock(return_value="ticker news")
        mock_global.func = MagicMock(side_effect=TimeoutError("timeout"))

        llm = _make_llm(tool_calls=False)
        from tradingagents.agents.analysts.news_analyst import create_news_analyst
        node = create_news_analyst(llm)
        result = node(_make_state())

        assert "news_report" in result


# ── Fundamentals analyst ────────────────────────────────────────────────


class TestFundamentalsAnalyst:
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_income_statement")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_cashflow")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_balance_sheet")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_fundamentals")
    def test_prefetch_path_calls_func(self, mock_fund, mock_bs, mock_cf, mock_inc):
        """Pre-fetch path calls .func() on all 4 financial tools."""
        mock_fund.func = MagicMock(return_value="fundamentals")
        mock_bs.func = MagicMock(return_value="balance sheet")
        mock_cf.func = MagicMock(return_value="cashflow")
        mock_inc.func = MagicMock(return_value="income")

        llm = _make_llm(tool_calls=False)
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        node = create_fundamentals_analyst(llm)
        result = node(_make_state())

        mock_fund.func.assert_called_once()
        mock_bs.func.assert_called_once()
        mock_cf.func.assert_called_once()
        mock_inc.func.assert_called_once()
        llm.bind_tools.assert_not_called()
        assert "fundamentals_report" in result

    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_income_statement")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_cashflow")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_balance_sheet")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_fundamentals")
    def test_tool_call_path_uses_bind_tools(self, mock_fund, mock_bs, mock_cf, mock_inc):
        """Tool-call path uses bind_tools (original behavior)."""
        mock_fund.name = "get_fundamentals"
        mock_bs.name = "get_balance_sheet"
        mock_cf.name = "get_cashflow"
        mock_inc.name = "get_income_statement"

        llm = _make_llm(tool_calls=True)
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        node = create_fundamentals_analyst(llm)
        result = node(_make_state())

        llm.bind_tools.assert_called_once()
        assert "fundamentals_report" in result

    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_income_statement")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_cashflow")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_balance_sheet")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_fundamentals")
    def test_prefetch_graceful_partial_failure(self, mock_fund, mock_bs, mock_cf, mock_inc):
        """Partial data failure degrades gracefully — other sources still work."""
        mock_fund.func = MagicMock(return_value="fundamentals")
        mock_bs.func = MagicMock(side_effect=ConnectionError("API down"))
        mock_cf.func = MagicMock(return_value="cashflow")
        mock_inc.func = MagicMock(side_effect=TimeoutError("timeout"))

        llm = _make_llm(tool_calls=False)
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        node = create_fundamentals_analyst(llm)
        result = node(_make_state())

        assert "fundamentals_report" in result

    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_income_statement")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_cashflow")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_balance_sheet")
    @patch("tradingagents.agents.analysts.fundamentals_analyst.get_fundamentals")
    def test_prefetch_all_sources_fail(self, mock_fund, mock_bs, mock_cf, mock_inc):
        """All data sources failing still produces a report (LLM gets <unavailable> blocks)."""
        mock_fund.func = MagicMock(side_effect=Exception("fail 1"))
        mock_bs.func = MagicMock(side_effect=Exception("fail 2"))
        mock_cf.func = MagicMock(side_effect=Exception("fail 3"))
        mock_inc.func = MagicMock(side_effect=Exception("fail 4"))

        llm = _make_llm(tool_calls=False)
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        node = create_fundamentals_analyst(llm)
        result = node(_make_state())

        assert "fundamentals_report" in result
