import unittest
from datetime import date
from unittest.mock import Mock, patch

from tradingagents.agents.utils.social_data_tools import (
    get_social_sentiment,
    has_social_sentiment_support,
)


class SocialDataToolsTest(unittest.TestCase):
    def test_support_flag_requires_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(has_social_sentiment_support())

        with patch.dict("os.environ", {"ADANOS_API_KEY": "sk_test"}, clear=True):
            self.assertTrue(has_social_sentiment_support())

    @patch("tradingagents.agents.utils.social_data_tools.requests.get")
    def test_historical_trade_dates_do_not_hit_network(self, mock_get):
        with patch.dict("os.environ", {"ADANOS_API_KEY": "sk_test"}, clear=True):
            result = get_social_sentiment.invoke(
                {"ticker": "TSLA", "curr_date": "2024-01-15", "look_back_days": 7}
            )

        self.assertIn("historical trade date", result)
        mock_get.assert_not_called()

    @patch("tradingagents.agents.utils.social_data_tools.requests.get")
    def test_formats_cross_source_snapshot(self, mock_get):
        reddit_response = Mock()
        reddit_response.raise_for_status.return_value = None
        reddit_response.json.return_value = {
            "stocks": [
                {
                    "ticker": "TSLA",
                    "mentions": 647,
                    "buzz_score": 81.2,
                    "bullish_pct": 46,
                    "trend": "rising",
                    "subreddit_count": 23,
                    "total_upvotes": 4120,
                }
            ]
        }

        x_response = Mock()
        x_response.raise_for_status.return_value = None
        x_response.json.return_value = {
            "stocks": [
                {
                    "ticker": "TSLA",
                    "mentions": 2650,
                    "buzz_score": 86.4,
                    "bullish_pct": 58,
                    "trend": "falling",
                    "unique_tweets": 392,
                    "total_upvotes": 95000,
                }
            ]
        }

        polymarket_response = Mock()
        polymarket_response.raise_for_status.return_value = None
        polymarket_response.json.return_value = {
            "stocks": [
                {
                    "ticker": "TSLA",
                    "trade_count": 3731,
                    "market_count": 71,
                    "buzz_score": 55.7,
                    "bullish_pct": 72,
                    "trend": "stable",
                    "total_liquidity": 8400000,
                }
            ]
        }

        mock_get.side_effect = [reddit_response, x_response, polymarket_response]

        with patch.dict("os.environ", {"ADANOS_API_KEY": "sk_test"}, clear=True):
            with patch("tradingagents.agents.utils.social_data_tools.date") as mock_date:
                mock_date.today.return_value = date(2026, 3, 19)
                result = get_social_sentiment.invoke(
                    {"ticker": "TSLA", "curr_date": "2026-03-19", "look_back_days": 7}
                )

        self.assertIn("## Social sentiment for TSLA", result)
        self.assertIn("Average buzz: 74.4/100", result)
        self.assertIn("Average bullish: 58.7%", result)
        self.assertIn("### Reddit", result)
        self.assertIn("### X/Twitter", result)
        self.assertIn("### Polymarket", result)
