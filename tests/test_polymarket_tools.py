"""
Tests for tradingagents.agents.utils.polymarket_tools

All HTTP calls are mocked with unittest.mock.patch so no live network access
is required.
"""

import json
import unittest
from unittest.mock import patch, MagicMock

from tradingagents.agents.utils.polymarket_tools import (
    _api_get,
    get_market_data,
    get_price_history,
    get_event_details,
    get_orderbook,
    get_event_news,
    get_global_news,
    get_whale_activity,
    get_market_stats,
    get_leaderboard_signals,
    get_social_sentiment,
    search_markets,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal Gamma event payload
# ---------------------------------------------------------------------------

def _gamma_event():
    return {
        "id": "123",
        "title": "Test Election 2026",
        "slug": "test-election-2026",
        "active": True,
        "startDate": "2026-01-01T00:00:00Z",
        "endDate": "2026-12-31T00:00:00Z",
        "volume": "500000",
        "liquidity": "50000",
        "description": "Who will win the 2026 test election?",
        "resolutionSource": "https://example.com",
        "tags": [{"label": "Politics"}],
        "markets": [
            {
                "question": "Will Candidate A win?",
                "conditionId": "cond-001",
                "active": True,
                "endDate": "2026-12-31T00:00:00Z",
                "outcomePrices": json.dumps(["0.60", "0.40"]),
                "outcomes": json.dumps(["Yes", "No"]),
                "spread": "0.02",
                "volume": "300000",
                "description": "Resolves YES if Candidate A wins.",
            }
        ],
    }


# ---------------------------------------------------------------------------
# _api_get
# ---------------------------------------------------------------------------

class TestApiGet(unittest.TestCase):

    @patch("tradingagents.agents.utils.polymarket_tools.requests.get")
    def test_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"key": "value"}
        mock_get.return_value = mock_resp

        result = _api_get("https://example.com/test")
        self.assertEqual(result, {"key": "value"})

    @patch("tradingagents.agents.utils.polymarket_tools.requests.get")
    @patch("tradingagents.agents.utils.polymarket_tools.time.sleep", return_value=None)
    def test_retry_then_raise(self, mock_sleep, mock_get):
        import requests as req
        mock_get.side_effect = req.ConnectionError("refused")
        with self.assertRaises(req.ConnectionError):
            _api_get("https://example.com/fail")
        self.assertEqual(mock_get.call_count, 3)


# ---------------------------------------------------------------------------
# get_market_data
# ---------------------------------------------------------------------------

class TestGetMarketData(unittest.TestCase):

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_returns_string(self, mock_api):
        mock_api.return_value = _gamma_event()
        result = get_market_data.invoke({"event_id": "123"})
        self.assertIsInstance(result, str)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_title(self, mock_api):
        mock_api.return_value = _gamma_event()
        result = get_market_data.invoke({"event_id": "123"})
        self.assertIn("Test Election 2026", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_volume(self, mock_api):
        mock_api.return_value = _gamma_event()
        result = get_market_data.invoke({"event_id": "123"})
        self.assertIn("500000", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_outcome_prices(self, mock_api):
        mock_api.return_value = _gamma_event()
        result = get_market_data.invoke({"event_id": "123"})
        self.assertIn("Yes", result)
        self.assertIn("0.60", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_error_handling(self, mock_api):
        mock_api.side_effect = Exception("network error")
        result = get_market_data.invoke({"event_id": "bad-id"})
        self.assertIsInstance(result, str)
        self.assertIn("Error", result)


# ---------------------------------------------------------------------------
# get_price_history
# ---------------------------------------------------------------------------

class TestGetPriceHistory(unittest.TestCase):

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_returns_string(self, mock_api):
        mock_api.return_value = {
            "history": [
                {"t": "2026-01-01T00:00:00Z", "p": 0.55},
                {"t": "2026-01-02T00:00:00Z", "p": 0.60},
                {"t": "2026-01-03T00:00:00Z", "p": 0.58},
            ]
        }
        result = get_price_history.invoke({"token_id": "tok-001"})
        self.assertIsInstance(result, str)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_stats(self, mock_api):
        mock_api.return_value = {
            "history": [
                {"t": "2026-01-01T00:00:00Z", "p": 0.5},
                {"t": "2026-01-02T00:00:00Z", "p": 0.7},
            ]
        }
        result = get_price_history.invoke({"token_id": "tok-001"})
        self.assertIn("Latest Price", result)
        self.assertIn("Min Price", result)
        self.assertIn("Max Price", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_empty_history(self, mock_api):
        mock_api.return_value = {"history": []}
        result = get_price_history.invoke({"token_id": "tok-001"})
        self.assertIn("No price history", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_error_handling(self, mock_api):
        mock_api.side_effect = Exception("timeout")
        result = get_price_history.invoke({"token_id": "bad-token"})
        self.assertIsInstance(result, str)
        self.assertIn("Error", result)


# ---------------------------------------------------------------------------
# get_event_details
# ---------------------------------------------------------------------------

class TestGetEventDetails(unittest.TestCase):

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_returns_string(self, mock_api):
        mock_api.return_value = _gamma_event()
        result = get_event_details.invoke({"event_id": "123"})
        self.assertIsInstance(result, str)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_description(self, mock_api):
        mock_api.return_value = _gamma_event()
        result = get_event_details.invoke({"event_id": "123"})
        self.assertIn("Who will win", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_resolution_deadline(self, mock_api):
        mock_api.return_value = _gamma_event()
        result = get_event_details.invoke({"event_id": "123"})
        self.assertIn("Resolution Deadline", result)
        self.assertIn("2026-12-31", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_market_question(self, mock_api):
        mock_api.return_value = _gamma_event()
        result = get_event_details.invoke({"event_id": "123"})
        self.assertIn("Will Candidate A win?", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_error_handling(self, mock_api):
        mock_api.side_effect = Exception("404")
        result = get_event_details.invoke({"event_id": "missing"})
        self.assertIsInstance(result, str)
        self.assertIn("Error", result)


# ---------------------------------------------------------------------------
# get_orderbook
# ---------------------------------------------------------------------------

class TestGetOrderbook(unittest.TestCase):

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_returns_string(self, mock_api):
        mock_api.return_value = {
            "market": "test-market",
            "asset_id": "tok-001",
            "bids": [{"price": "0.59", "size": "100"}, {"price": "0.58", "size": "200"}],
            "asks": [{"price": "0.61", "size": "150"}, {"price": "0.62", "size": "300"}],
        }
        result = get_orderbook.invoke({"token_id": "tok-001"})
        self.assertIsInstance(result, str)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_bids_and_asks(self, mock_api):
        mock_api.return_value = {
            "market": "test-market",
            "asset_id": "tok-001",
            "bids": [{"price": "0.59", "size": "100"}],
            "asks": [{"price": "0.61", "size": "150"}],
        }
        result = get_orderbook.invoke({"token_id": "tok-001"})
        self.assertIn("Bids", result)
        self.assertIn("Asks", result)
        self.assertIn("0.59", result)
        self.assertIn("0.61", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_spread_calculation(self, mock_api):
        mock_api.return_value = {
            "market": "test-market",
            "asset_id": "tok-001",
            "bids": [{"price": "0.58", "size": "100"}],
            "asks": [{"price": "0.62", "size": "100"}],
        }
        result = get_orderbook.invoke({"token_id": "tok-001"})
        self.assertIn("Spread", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_error_handling(self, mock_api):
        mock_api.side_effect = Exception("connection refused")
        result = get_orderbook.invoke({"token_id": "bad-token"})
        self.assertIsInstance(result, str)
        self.assertIn("Error", result)


# ---------------------------------------------------------------------------
# get_event_news
# ---------------------------------------------------------------------------

class TestGetEventNews(unittest.TestCase):

    def test_no_api_key_returns_message(self):
        import os
        os.environ.pop("TAVILY_API_KEY", None)
        result = get_event_news.invoke({"query": "test election"})
        self.assertIsInstance(result, str)
        self.assertIn("TAVILY_API_KEY", result)

    def test_with_mocked_tavily(self):
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {
                    "title": "Election Update",
                    "url": "https://news.example.com/1",
                    "content": "Candidate A leads in polls.",
                    "published_date": "2026-03-01",
                }
            ]
        }
        mock_tavily_module = MagicMock()
        mock_tavily_module.TavilyClient.return_value = mock_client

        with patch.dict("sys.modules", {"tavily": mock_tavily_module}):
            result = get_event_news.invoke({"query": "election 2026", "api_key": "fake-key"})

        self.assertIsInstance(result, str)
        self.assertIn("Election Update", result)
        self.assertIn("election 2026", result)

    def test_error_handling(self):
        mock_tavily_module = MagicMock()
        mock_tavily_module.TavilyClient.side_effect = Exception("API error")

        with patch.dict("sys.modules", {"tavily": mock_tavily_module}):
            result = get_event_news.invoke({"query": "test", "api_key": "fake-key-for-error-test"})

        self.assertIsInstance(result, str)
        self.assertIn("failed", result.lower())


# ---------------------------------------------------------------------------
# get_global_news
# ---------------------------------------------------------------------------

class TestGetGlobalNews(unittest.TestCase):

    def test_no_api_key_returns_message(self):
        import os
        os.environ.pop("TAVILY_API_KEY", None)
        result = get_global_news.invoke({})
        self.assertIsInstance(result, str)
        self.assertIn("TAVILY_API_KEY", result)

    def test_with_mocked_tavily(self):
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {
                    "title": "Global Markets Update",
                    "url": "https://finance.example.com/1",
                    "content": "Markets rose globally.",
                    "published_date": "2026-03-20",
                }
            ]
        }
        mock_tavily_module = MagicMock()
        mock_tavily_module.TavilyClient.return_value = mock_client

        with patch.dict("sys.modules", {"tavily": mock_tavily_module}):
            result = get_global_news.invoke({"query": "global markets 2026", "api_key": "fake-key"})

        self.assertIsInstance(result, str)
        self.assertIn("Global Markets Update", result)

    def test_error_returns_string(self):
        mock_tavily_module = MagicMock()
        mock_tavily_module.TavilyClient.side_effect = RuntimeError("rate limit")

        with patch.dict("sys.modules", {"tavily": mock_tavily_module}):
            result = get_global_news.invoke({"query": "test", "api_key": "fake-key-for-error-test"})

        self.assertIsInstance(result, str)
        self.assertIn("failed", result.lower())


# ---------------------------------------------------------------------------
# get_whale_activity
# ---------------------------------------------------------------------------

class TestGetWhaleActivity(unittest.TestCase):

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_returns_string(self, mock_api):
        mock_api.return_value = [
            {"proxyWallet": "0xABCDEF123456", "position": "10000", "value": "6000"},
            {"proxyWallet": "0x789012345678", "position": "5000", "value": "3000"},
        ]
        result = get_whale_activity.invoke({"market_id": "cond-001"})
        self.assertIsInstance(result, str)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_table_headers(self, mock_api):
        mock_api.return_value = [
            {"proxyWallet": "0xABCDEF1234567890", "position": "10000", "value": "6000"},
        ]
        result = get_whale_activity.invoke({"market_id": "cond-001"})
        self.assertIn("Rank", result)
        self.assertIn("Address", result)
        self.assertIn("Position", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_empty_holders(self, mock_api):
        mock_api.return_value = []
        result = get_whale_activity.invoke({"market_id": "cond-001"})
        self.assertIsInstance(result, str)
        self.assertIn("No holder data", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_error_handling(self, mock_api):
        mock_api.side_effect = Exception("server error")
        result = get_whale_activity.invoke({"market_id": "bad-market"})
        self.assertIsInstance(result, str)
        self.assertIn("Error", result)


# ---------------------------------------------------------------------------
# get_market_stats
# ---------------------------------------------------------------------------

class TestGetMarketStats(unittest.TestCase):

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_returns_string(self, mock_api):
        mock_api.return_value = {
            "openInterest": "250000",
            "totalVolume": "500000",
            "numTraders": "1234",
            "liquidity": "75000",
            "lastTradePrice": "0.62",
        }
        result = get_market_stats.invoke({"market_id": "cond-001"})
        self.assertIsInstance(result, str)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_open_interest(self, mock_api):
        mock_api.return_value = {
            "openInterest": "250000",
            "totalVolume": "500000",
            "numTraders": "1234",
            "liquidity": "75000",
            "lastTradePrice": "0.62",
        }
        result = get_market_stats.invoke({"market_id": "cond-001"})
        self.assertIn("Open Interest", result)
        self.assertIn("250000", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_volume(self, mock_api):
        mock_api.return_value = {
            "openInterest": "250000",
            "totalVolume": "500000",
        }
        result = get_market_stats.invoke({"market_id": "cond-001"})
        self.assertIn("Volume", result)
        self.assertIn("500000", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_error_handling(self, mock_api):
        mock_api.side_effect = Exception("404 not found")
        result = get_market_stats.invoke({"market_id": "missing"})
        self.assertIsInstance(result, str)
        self.assertIn("Error", result)


# ---------------------------------------------------------------------------
# get_leaderboard_signals
# ---------------------------------------------------------------------------

class TestGetLeaderboardSignals(unittest.TestCase):

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_returns_string(self, mock_api):
        mock_api.return_value = [
            {"name": "TraderAlpha", "pnl": "12000", "volume": "300000"},
            {"name": "TraderBeta", "pnl": "9000", "volume": "250000"},
        ]
        result = get_leaderboard_signals.invoke({"category": "OVERALL", "time_period": "WEEK"})
        self.assertIsInstance(result, str)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_traders(self, mock_api):
        mock_api.return_value = [
            {"name": "TraderAlpha", "pnl": "12000", "volume": "300000"},
        ]
        result = get_leaderboard_signals.invoke({"category": "OVERALL", "time_period": "WEEK"})
        self.assertIn("TraderAlpha", result)
        self.assertIn("12000", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_empty_leaderboard(self, mock_api):
        mock_api.return_value = []
        result = get_leaderboard_signals.invoke({})
        self.assertIsInstance(result, str)
        self.assertIn("No leaderboard data", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_error_handling(self, mock_api):
        mock_api.side_effect = Exception("unauthorized")
        result = get_leaderboard_signals.invoke({"category": "POLITICS", "time_period": "MONTH"})
        self.assertIsInstance(result, str)
        self.assertIn("Error", result)


# ---------------------------------------------------------------------------
# get_social_sentiment
# ---------------------------------------------------------------------------

class TestGetSocialSentiment(unittest.TestCase):

    def test_no_keys_graceful(self):
        import os
        for key in ("TWITTER_BEARER_TOKEN", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"):
            os.environ.pop(key, None)
        result = get_social_sentiment.invoke({"query": "polymarket election"})
        self.assertIsInstance(result, str)
        self.assertIn("skipping", result.lower())

    def test_twitter_with_mock(self):
        mock_tweet = MagicMock()
        mock_tweet.text = "Candidate A is looking strong on Polymarket!"
        mock_tweet.public_metrics = {"like_count": 10, "retweet_count": 2}

        mock_client = MagicMock()
        mock_client.search_recent_tweets.return_value = MagicMock(data=[mock_tweet])

        mock_tweepy = MagicMock()
        mock_tweepy.Client.return_value = mock_client

        with patch.dict("sys.modules", {"tweepy": mock_tweepy}):
            with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "fake-token"}):
                result = get_social_sentiment.invoke({"query": "polymarket election"})

        self.assertIsInstance(result, str)
        self.assertIn("Twitter", result)
        self.assertIn("Candidate A", result)

    def test_reddit_with_mock(self):
        mock_post = MagicMock()
        mock_post.title = "Polymarket odds for election shifting"
        mock_post.score = 150
        mock_post.subreddit.display_name = "Polymarket"

        mock_reddit_instance = MagicMock()
        mock_reddit_instance.subreddit.return_value.search.return_value = [mock_post]

        mock_praw = MagicMock()
        mock_praw.Reddit.return_value = mock_reddit_instance

        with patch.dict("sys.modules", {"praw": mock_praw}):
            with patch.dict("os.environ", {
                "REDDIT_CLIENT_ID": "fake-id",
                "REDDIT_CLIENT_SECRET": "fake-secret",
            }):
                # Remove Twitter token so we focus on Reddit
                import os
                os.environ.pop("TWITTER_BEARER_TOKEN", None)
                result = get_social_sentiment.invoke({"query": "polymarket"})

        self.assertIsInstance(result, str)
        self.assertIn("Reddit", result)
        self.assertIn("Polymarket odds", result)

    def test_error_in_twitter_graceful(self):
        mock_tweepy = MagicMock()
        mock_tweepy.Client.side_effect = Exception("auth error")

        with patch.dict("sys.modules", {"tweepy": mock_tweepy}):
            with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "fake-token"}):
                import os
                os.environ.pop("REDDIT_CLIENT_ID", None)
                result = get_social_sentiment.invoke({"query": "test"})

        self.assertIsInstance(result, str)
        # Should not raise; should contain Twitter section mention
        self.assertIn("Twitter", result)


# ---------------------------------------------------------------------------
# search_markets
# ---------------------------------------------------------------------------

class TestSearchMarkets(unittest.TestCase):

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_returns_string(self, mock_api):
        mock_api.return_value = [
            {"title": "US Election 2026", "volume": "1000000", "endDate": "2026-11-03", "active": True},
            {"title": "Super Bowl 2026", "volume": "500000", "endDate": "2026-02-07", "active": True},
        ]
        result = search_markets.invoke({"min_volume": 10000})
        self.assertIsInstance(result, str)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_contains_market_titles(self, mock_api):
        mock_api.return_value = [
            {"title": "US Election 2026", "volume": "1000000", "endDate": "2026-11-03", "active": True},
        ]
        result = search_markets.invoke({"min_volume": 10000})
        self.assertIn("US Election 2026", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_volume_filter(self, mock_api):
        mock_api.return_value = [
            {"title": "Big Market", "volume": "1000000", "endDate": "2026-11-03", "active": True},
            {"title": "Small Market", "volume": "500", "endDate": "2026-11-03", "active": True},
        ]
        result = search_markets.invoke({"min_volume": 10000})
        self.assertIn("Big Market", result)
        self.assertNotIn("Small Market", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_empty_results(self, mock_api):
        mock_api.return_value = []
        result = search_markets.invoke({"min_volume": 10000})
        self.assertIsInstance(result, str)
        self.assertIn("No markets matched", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_error_handling(self, mock_api):
        mock_api.side_effect = Exception("server down")
        result = search_markets.invoke({"min_volume": 10000})
        self.assertIsInstance(result, str)
        self.assertIn("Error", result)

    @patch("tradingagents.agents.utils.polymarket_tools._api_get")
    def test_category_filter_passed_to_api(self, mock_api):
        mock_api.return_value = [
            {"title": "Politics Market", "volume": "500000", "endDate": "2026-12-01", "active": True},
        ]
        result = search_markets.invoke({"min_volume": 1000, "category": "politics"})
        self.assertIsInstance(result, str)
        # Verify category was passed in params
        call_kwargs = mock_api.call_args
        params = call_kwargs[1].get("params", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {})
        self.assertEqual(params.get("tag"), "politics")


if __name__ == "__main__":
    unittest.main()
