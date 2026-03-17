"""Integration tests for scanner vendor routing.

Verifies that when config says scanner_data=alpha_vantage,
scanner tools route to Alpha Vantage implementations.
"""

import pytest
from tradingagents.dataflows.interface import route_to_vendor, get_vendor
from tradingagents.dataflows.config import set_config


@pytest.mark.integration
class TestScannerRouting:

    def setup_method(self):
        """Set config to use alpha_vantage for scanner_data."""
        from tradingagents.default_config import DEFAULT_CONFIG

        config = DEFAULT_CONFIG.copy()
        config["data_vendors"]["scanner_data"] = "alpha_vantage"
        set_config(config)

    def test_vendor_resolves_to_alpha_vantage(self):
        vendor = get_vendor("scanner_data")
        assert vendor == "alpha_vantage"

    def test_market_movers_routes_to_av(self, av_api_key):
        result = route_to_vendor("get_market_movers", "day_gainers")
        assert isinstance(result, str)
        assert "Market Movers" in result

    def test_market_indices_routes_to_av(self, av_api_key):
        result = route_to_vendor("get_market_indices")
        assert isinstance(result, str)
        assert "Market Indices" in result or "Index" in result

    def test_sector_performance_routes_to_av(self, av_api_key):
        result = route_to_vendor("get_sector_performance")
        assert isinstance(result, str)
        assert "Sector" in result

    def test_industry_performance_routes_to_av(self, av_api_key):
        result = route_to_vendor("get_industry_performance", "technology")
        assert isinstance(result, str)
        assert "|" in result

    def test_topic_news_routes_to_av(self, av_api_key):
        result = route_to_vendor("get_topic_news", "market", limit=3)
        assert isinstance(result, str)
        assert "News" in result


class TestFallbackRouting:

    def setup_method(self):
        """Set config to use yfinance as fallback."""
        from tradingagents.default_config import DEFAULT_CONFIG

        config = DEFAULT_CONFIG.copy()
        config["data_vendors"]["scanner_data"] = "yfinance"
        set_config(config)

    def test_yfinance_fallback_works(self):
        """When configured for yfinance, scanner tools should use yfinance."""
        result = route_to_vendor("get_market_movers", "day_gainers")
        assert isinstance(result, str)
        assert "Market Movers" in result
