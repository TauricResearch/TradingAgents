"""Tests for the LangChain tool wrappers in agents/utils/.

Verifies that each tool correctly routes arguments to the dataflow layer
and that get_indicators handles comma-separated indicator strings.
"""

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# get_indicators comma-splitting logic
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetIndicatorsCommaSplit:
    @patch("tradingagents.agents.utils.technical_indicators_tools.route_to_vendor")
    def test_single_indicator(self, mock_route):
        from tradingagents.agents.utils.technical_indicators_tools import get_indicators
        mock_route.return_value = "RSI data"

        result = get_indicators.invoke({
            "symbol": "AAPL",
            "indicator": "rsi",
            "curr_date": "2026-01-15",
        })
        assert result == "RSI data"
        mock_route.assert_called_once_with("get_indicators", "AAPL", "rsi", "2026-01-15", 30)

    @patch("tradingagents.agents.utils.technical_indicators_tools.route_to_vendor")
    def test_comma_separated_indicators(self, mock_route):
        from tradingagents.agents.utils.technical_indicators_tools import get_indicators
        mock_route.side_effect = lambda *args: f"{args[2]} data"

        result = get_indicators.invoke({
            "symbol": "NVDA",
            "indicator": "rsi, macd, bbands",
            "curr_date": "2026-01-15",
        })
        assert "rsi data" in result
        assert "macd data" in result
        assert "bbands data" in result
        assert mock_route.call_count == 3

    @patch("tradingagents.agents.utils.technical_indicators_tools.route_to_vendor")
    def test_indicator_lowercased(self, mock_route):
        from tradingagents.agents.utils.technical_indicators_tools import get_indicators
        mock_route.return_value = "ok"

        get_indicators.invoke({
            "symbol": "AAPL",
            "indicator": "RSI",
            "curr_date": "2026-01-15",
        })
        mock_route.assert_called_once_with("get_indicators", "AAPL", "rsi", "2026-01-15", 30)

    @patch("tradingagents.agents.utils.technical_indicators_tools.route_to_vendor")
    def test_custom_look_back_days(self, mock_route):
        from tradingagents.agents.utils.technical_indicators_tools import get_indicators
        mock_route.return_value = "ok"

        get_indicators.invoke({
            "symbol": "AAPL",
            "indicator": "rsi",
            "curr_date": "2026-01-15",
            "look_back_days": 60,
        })
        mock_route.assert_called_once_with("get_indicators", "AAPL", "rsi", "2026-01-15", 60)

    @patch("tradingagents.agents.utils.technical_indicators_tools.route_to_vendor")
    def test_individual_indicator_error_captured(self, mock_route):
        from tradingagents.agents.utils.technical_indicators_tools import get_indicators

        def side_effect(*args):
            if args[2] == "bad_ind":
                raise ValueError("Unknown indicator: bad_ind")
            return f"{args[2]} data"

        mock_route.side_effect = side_effect

        result = get_indicators.invoke({
            "symbol": "AAPL",
            "indicator": "rsi, bad_ind, macd",
            "curr_date": "2026-01-15",
        })
        assert "rsi data" in result
        assert "Unknown indicator: bad_ind" in result
        assert "macd data" in result

    @patch("tradingagents.agents.utils.technical_indicators_tools.route_to_vendor")
    def test_empty_indicator_parts_skipped(self, mock_route):
        from tradingagents.agents.utils.technical_indicators_tools import get_indicators
        mock_route.return_value = "data"

        get_indicators.invoke({
            "symbol": "AAPL",
            "indicator": "rsi,,, macd,",
            "curr_date": "2026-01-15",
        })
        assert mock_route.call_count == 2


# ---------------------------------------------------------------------------
# Core stock data tool routing
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCoreStockTool:
    @patch("tradingagents.agents.utils.core_stock_tools.route_to_vendor")
    def test_get_stock_data_routes_correctly(self, mock_route):
        from tradingagents.agents.utils.core_stock_tools import get_stock_data
        mock_route.return_value = "OHLCV data"

        result = get_stock_data.invoke({
            "symbol": "AAPL",
            "start_date": "2026-01-01",
            "end_date": "2026-01-15",
        })
        assert result == "OHLCV data"
        mock_route.assert_called_once_with("get_stock_data", "AAPL", "2026-01-01", "2026-01-15")


# ---------------------------------------------------------------------------
# Fundamental data tools routing
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFundamentalDataTools:
    @patch("tradingagents.agents.utils.fundamental_data_tools.route_to_vendor")
    def test_get_fundamentals(self, mock_route):
        from tradingagents.agents.utils.fundamental_data_tools import get_fundamentals
        mock_route.return_value = "Fundamentals report"

        result = get_fundamentals.invoke({"ticker": "AAPL", "curr_date": "2026-01-15"})
        assert result == "Fundamentals report"
        mock_route.assert_called_once_with("get_fundamentals", "AAPL", "2026-01-15")

    @patch("tradingagents.agents.utils.fundamental_data_tools.route_to_vendor")
    def test_get_balance_sheet(self, mock_route):
        from tradingagents.agents.utils.fundamental_data_tools import get_balance_sheet
        mock_route.return_value = "Balance sheet"

        result = get_balance_sheet.invoke({"ticker": "AAPL"})
        assert result == "Balance sheet"

    @patch("tradingagents.agents.utils.fundamental_data_tools.route_to_vendor")
    def test_get_cashflow(self, mock_route):
        from tradingagents.agents.utils.fundamental_data_tools import get_cashflow
        mock_route.return_value = "Cash flow"

        result = get_cashflow.invoke({"ticker": "AAPL"})
        assert result == "Cash flow"

    @patch("tradingagents.agents.utils.fundamental_data_tools.route_to_vendor")
    def test_get_income_statement(self, mock_route):
        from tradingagents.agents.utils.fundamental_data_tools import (
            get_income_statement,
        )
        mock_route.return_value = "Income statement"

        result = get_income_statement.invoke({"ticker": "AAPL"})
        assert result == "Income statement"


# ---------------------------------------------------------------------------
# News data tools routing
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNewsDataTools:
    @patch("tradingagents.agents.utils.news_data_tools.route_to_vendor")
    def test_get_news(self, mock_route):
        from tradingagents.agents.utils.news_data_tools import get_news
        mock_route.return_value = "News data"

        result = get_news.invoke({
            "ticker": "NVDA",
            "start_date": "2026-01-01",
            "end_date": "2026-01-15",
        })
        assert result == "News data"
        mock_route.assert_called_once_with("get_news", "NVDA", "2026-01-01", "2026-01-15")

    @patch("tradingagents.agents.utils.news_data_tools.route_to_vendor")
    def test_get_insider_transactions(self, mock_route):
        from tradingagents.agents.utils.news_data_tools import get_insider_transactions
        mock_route.return_value = "Insider data"

        result = get_insider_transactions.invoke({"ticker": "AAPL"})
        assert result == "Insider data"
        mock_route.assert_called_once_with("get_insider_transactions", "AAPL")

    @patch("tradingagents.agents.utils.news_data_tools.route_to_vendor")
    def test_get_global_news(self, mock_route):
        from tradingagents.agents.utils.news_data_tools import get_global_news
        mock_route.return_value = "Global news"

        result = get_global_news.invoke({"curr_date": "2026-01-15"})
        assert result == "Global news"
