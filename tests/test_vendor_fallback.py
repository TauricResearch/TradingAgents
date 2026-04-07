import unittest
from unittest.mock import patch

from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.vendor_exceptions import VendorConfigurationError, VendorInputError, VendorMalformedResponseError


class VendorFallbackTests(unittest.TestCase):
    def test_rate_limit_falls_back_to_next_vendor(self):
        with patch("tradingagents.dataflows.interface.get_vendor", return_value="alpha_vantage,yfinance"), patch.dict(
            "tradingagents.dataflows.interface.VENDOR_METHODS",
            {
                "get_company_news": {
                    "alpha_vantage": lambda *_args, **_kwargs: (_ for _ in ()).throw(AlphaVantageRateLimitError("rate")),
                    "yfinance": lambda *_args, **_kwargs: "yfinance result",
                }
            },
            clear=False,
        ):
            result = route_to_vendor("get_company_news", "AAPL", "2026-04-01", "2026-04-02")

        self.assertEqual(result, "yfinance result")

    def test_generic_exception_falls_back_to_next_vendor(self):
        with patch("tradingagents.dataflows.interface.get_vendor", return_value="alpha_vantage,yfinance"), patch.dict(
            "tradingagents.dataflows.interface.VENDOR_METHODS",
            {
                "get_company_news": {
                    "alpha_vantage": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
                    "yfinance": lambda *_args, **_kwargs: "fallback result",
                }
            },
            clear=False,
        ):
            result = route_to_vendor("get_company_news", "AAPL", "2026-04-01", "2026-04-02")

        self.assertEqual(result, "fallback result")

    def test_empty_result_falls_back_to_next_vendor(self):
        with patch("tradingagents.dataflows.interface.get_vendor", return_value="alpha_vantage,yfinance"), patch.dict(
            "tradingagents.dataflows.interface.VENDOR_METHODS",
            {
                "get_company_news": {
                    "alpha_vantage": lambda *_args, **_kwargs: "No news found for AAPL",
                    "yfinance": lambda *_args, **_kwargs: "usable result",
                }
            },
            clear=False,
        ):
            result = route_to_vendor("get_company_news", "AAPL", "2026-04-01", "2026-04-02")

        self.assertEqual(result, "usable result")

    def test_malformed_payload_falls_back_to_next_vendor(self):
        with patch("tradingagents.dataflows.interface.get_vendor", return_value="alpha_vantage,yfinance"), patch.dict(
            "tradingagents.dataflows.interface.VENDOR_METHODS",
            {
                "get_company_news": {
                    "alpha_vantage": lambda *_args, **_kwargs: (_ for _ in ()).throw(VendorMalformedResponseError("bad payload")),
                    "yfinance": lambda *_args, **_kwargs: "usable result",
                }
            },
            clear=False,
        ):
            result = route_to_vendor("get_company_news", "AAPL", "2026-04-01", "2026-04-02")

        self.assertEqual(result, "usable result")

    def test_invalid_user_input_raises_without_fallback(self):
        with self.assertRaises(VendorInputError):
            route_to_vendor("get_company_news", "AAPL", "2026/04/01", "2026-04-02")

    def test_social_sentiment_degrades_gracefully_when_primary_provider_missing(self):
        with patch("tradingagents.dataflows.interface.get_vendor", return_value="naver,yfinance"), patch.dict(
            "tradingagents.dataflows.interface.VENDOR_METHODS",
            {
                "get_social_sentiment": {
                    "naver": lambda *_args, **_kwargs: (_ for _ in ()).throw(VendorConfigurationError("missing naver key")),
                    "yfinance": lambda *_args, **_kwargs: "Dedicated social provider unavailable; using news-derived sentiment for AAPL.",
                }
            },
            clear=False,
        ):
            result = route_to_vendor("get_social_sentiment", "AAPL", "2026-04-01", "2026-04-02")

        self.assertIn("Dedicated social provider unavailable", result)
        self.assertIn("news-derived sentiment", result)


if __name__ == "__main__":
    unittest.main()
