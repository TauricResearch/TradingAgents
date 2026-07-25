"""Tests for A-share vs non-A-share sentiment analyst routing."""

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst
from tradingagents.agents.schemas import SentimentBand, SentimentReport


def _structured_llm(captured: dict):
    report = SentimentReport(
        overall_band=SentimentBand.NEUTRAL,
        overall_score=5.0,
        confidence="medium",
        narrative="neutral",
    )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or report
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def _state(ticker: str):
    return {
        "company_of_interest": ticker,
        "trade_date": "2026-07-23",
        "asset_type": "stock",
        "messages": [],
    }


def _mock_route(*args, **kwargs):
    return f"[{args[0]} data]"


@pytest.mark.unit
class TestSentimentAnalystRouting:
    @patch("tradingagents.agents.analysts.sentiment_analyst.fetch_stocktwits_messages")
    @patch("tradingagents.agents.analysts.sentiment_analyst.fetch_reddit_posts")
    @patch("tradingagents.agents.utils.news_data_tools.route_to_vendor")
    @patch("tradingagents.agents.analysts.sentiment_analyst.route_to_vendor")
    def test_a_share_uses_capital_flow_sources(
        self, mock_route, mock_news_route, mock_reddit, mock_stocktwits
    ):
        mock_route.side_effect = _mock_route
        mock_news_route.return_value = "news data"
        captured = {}
        analyst = create_sentiment_analyst(_structured_llm(captured))
        analyst(_state("600519.SH"))

        prompt = str(captured["prompt"])
        # A-share prompt has capital-flow blocks, not Reddit/StockTwits data
        assert "Northbound" in prompt
        assert "Margin financing" in prompt
        assert "Insider trades" in prompt
        assert "<start_of_stocktwits>" not in prompt
        assert "<start_of_reddit>" not in prompt
        assert "r/wallstreetbets" not in prompt
        # reality_gap instructed to stay null for A-share
        assert "Leave null" in prompt or "leave null" in prompt.lower()
        # route_to_vendor called for all A-share sentiment sources
        methods = [call.args[0] for call in mock_route.call_args_list]
        assert "get_a_share_northbound_flow" in methods
        assert "get_a_share_northbound_holdings" in methods
        assert "get_a_share_margin_financing" in methods
        assert "get_a_share_insider_trades" in methods
        assert "get_a_share_dragon_tiger" in methods  # enabled by default

    @patch("tradingagents.agents.analysts.sentiment_analyst.fetch_stocktwits_messages")
    @patch("tradingagents.agents.analysts.sentiment_analyst.fetch_reddit_posts")
    @patch("tradingagents.agents.utils.news_data_tools.route_to_vendor")
    @patch("tradingagents.agents.analysts.sentiment_analyst.route_to_vendor")
    def test_us_share_uses_reddit_stocktwits(
        self, mock_route, mock_news_route, mock_reddit, mock_stocktwits
    ):
        mock_news_route.return_value = "news data"
        mock_reddit.return_value = "reddit data"
        mock_stocktwits.return_value = "stocktwits data"
        captured = {}
        analyst = create_sentiment_analyst(_structured_llm(captured))
        analyst(_state("AAPL"))

        prompt = str(captured["prompt"])
        assert "StockTwits" in prompt
        assert "Reddit" in prompt
        assert "Northbound" not in prompt
        # A-share route not called for US ticker
        methods = [call.args[0] for call in mock_route.call_args_list]
        assert "get_a_share_northbound_flow" not in methods
        assert mock_reddit.called
        assert mock_stocktwits.called

    @patch("tradingagents.agents.analysts.sentiment_analyst.fetch_stocktwits_messages")
    @patch("tradingagents.agents.analysts.sentiment_analyst.fetch_reddit_posts")
    @patch("tradingagents.agents.utils.news_data_tools.route_to_vendor")
    @patch("tradingagents.agents.analysts.sentiment_analyst.route_to_vendor")
    def test_a_share_dragon_tiger_disabled(
        self, mock_route, mock_news_route, mock_reddit, mock_stocktwits, monkeypatch
    ):
        monkeypatch.setattr(
            "tradingagents.agents.analysts.sentiment_analyst.get_config",
            lambda: {"sentiment_a_share_dragon_tiger_enabled": False},
        )
        mock_route.side_effect = _mock_route
        mock_news_route.return_value = "news data"
        captured = {}
        analyst = create_sentiment_analyst(_structured_llm(captured))
        analyst(_state("600519.SH"))

        methods = [call.args[0] for call in mock_route.call_args_list]
        assert "get_a_share_dragon_tiger" not in methods
        # Other A-share sources are still fetched
        assert "get_a_share_northbound_flow" in methods
        assert "get_a_share_margin_financing" in methods

    @patch("tradingagents.agents.analysts.sentiment_analyst.fetch_stocktwits_messages")
    @patch("tradingagents.agents.analysts.sentiment_analyst.fetch_reddit_posts")
    @patch("tradingagents.agents.utils.news_data_tools.route_to_vendor")
    @patch("tradingagents.agents.analysts.sentiment_analyst.route_to_vendor")
    def test_a_share_fail_open_on_source_error(
        self, mock_route, mock_news_route, mock_reddit, mock_stocktwits
    ):
        # One A-share source raises; the report must still be produced.
        def flaky_route(*args, **kwargs):
            if args[0] == "get_a_share_margin_financing":
                raise RuntimeError("vendor outage")
            return f"[{args[0]} data]"

        mock_route.side_effect = flaky_route
        mock_news_route.return_value = "news data"
        captured = {}
        analyst = create_sentiment_analyst(_structured_llm(captured))
        result = analyst(_state("600519.SH"))

        # Report produced despite one source failing
        assert result["sentiment_report"] is not None
        prompt = str(captured["prompt"])
        assert "margin_financing unavailable" in prompt
        assert "Northbound" in prompt  # other blocks present
