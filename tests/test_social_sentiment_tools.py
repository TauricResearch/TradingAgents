import unittest
from unittest.mock import patch

from tradingagents.agents.utils.social_data_tools import get_social_sentiment as social_tool
from tradingagents.dataflows import adanos_social, interface


class SocialSentimentToolTests(unittest.TestCase):
    def test_route_to_vendor_supports_social_data(self):
        with patch.dict(
            interface.VENDOR_METHODS["get_social_sentiment"],
            {"adanos": lambda ticker, curr_date, look_back_days: f"{ticker}|{curr_date}|{look_back_days}"},
            clear=True,
        ):
            result = interface.route_to_vendor("get_social_sentiment", "NVDA", "2026-01-15", 5)

        self.assertEqual(result, "NVDA|2026-01-15|5")

    def test_social_tool_routes_to_vendor(self):
        with patch("tradingagents.agents.utils.social_data_tools.route_to_vendor", return_value="ok") as mock_route:
            result = social_tool.invoke(
                {"ticker": "NVDA", "curr_date": "2026-01-15", "look_back_days": 7}
            )

        self.assertEqual(result, "ok")
        mock_route.assert_called_once_with("get_social_sentiment", "NVDA", "2026-01-15", 7)

    def test_adanos_social_formats_multiple_sources(self):
        payloads = {
            "/reddit/stocks/v1/stock/NVDA": {
                "company_name": "NVIDIA Corporation",
                "buzz_score": 72.4,
                "sentiment_score": 0.31,
                "bullish_pct": 61,
                "bearish_pct": 18,
                "trend": "rising",
                "total_mentions": 142,
                "unique_posts": 48,
            },
            "/news/stocks/v1/stock/NVDA": {
                "source_count": 23,
                "sentiment_score": 0.22,
                "bullish_pct": 54,
                "bearish_pct": 16,
            },
            "/x/stocks/v1/stock/NVDA": {
                "unique_tweets": 305,
                "sentiment_score": 0.27,
                "trend": "rising",
            },
            "/polymarket/stocks/v1/stock/NVDA": {
                "trade_count": 91,
                "market_count": 4,
                "total_liquidity": 120000.0,
                "sentiment_score": 0.14,
            },
        }

        def fake_request(path, *, api_key, base_url, params):
            self.assertEqual(api_key, "test-key")
            self.assertEqual(base_url, "https://api.adanos.org")
            self.assertEqual(params, {"days": 7})
            return payloads[path]

        with patch.dict("os.environ", {"ADANOS_API_KEY": "test-key"}, clear=False):
            with patch("tradingagents.dataflows.adanos_social._request_json", side_effect=fake_request):
                result = adanos_social.get_social_sentiment("NVDA", "2026-01-15", 7)

        self.assertIn("# NVDA Adanos social sentiment", result)
        self.assertIn("## Reddit", result)
        self.assertIn("## News", result)
        self.assertIn("## X/Twitter", result)
        self.assertIn("## Polymarket", result)
        self.assertIn("Buzz score: 72.4", result)
        self.assertIn("Trades: 91", result)

    def test_adanos_social_requires_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = adanos_social.get_social_sentiment("NVDA", "2026-01-15", 7)

        self.assertIn("ADANOS_API_KEY", result)


if __name__ == "__main__":
    unittest.main()
