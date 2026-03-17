"""Integration tests for Alpha Vantage scanner data layer.

All tests hit the real Alpha Vantage API — no mocks.
Requires ALPHA_VANTAGE_API_KEY environment variable.
"""

import pytest

from tradingagents.dataflows.alpha_vantage_scanner import (
    get_market_movers_alpha_vantage,
    get_market_indices_alpha_vantage,
    get_sector_performance_alpha_vantage,
    get_industry_performance_alpha_vantage,
    get_topic_news_alpha_vantage,
)


@pytest.mark.integration
class TestMarketMovers:

    def test_day_gainers(self, av_api_key):
        result = get_market_movers_alpha_vantage("day_gainers")
        assert isinstance(result, str)
        assert "Market Movers" in result
        assert "|" in result  # markdown table

    def test_day_losers(self, av_api_key):
        result = get_market_movers_alpha_vantage("day_losers")
        assert isinstance(result, str)
        assert "Market Movers" in result

    def test_most_actives(self, av_api_key):
        result = get_market_movers_alpha_vantage("most_actives")
        assert isinstance(result, str)
        assert "Market Movers" in result

    def test_invalid_category_raises(self, av_api_key):
        with pytest.raises(ValueError):
            get_market_movers_alpha_vantage("invalid_category")


@pytest.mark.integration
class TestMarketIndices:

    def test_returns_markdown_table(self, av_api_key):
        result = get_market_indices_alpha_vantage()
        assert isinstance(result, str)
        assert "Market Indices" in result
        assert "|" in result
        # Should contain at least some index proxies
        assert any(name in result for name in ["S&P 500", "SPY", "Dow", "DIA", "NASDAQ", "QQQ"])


@pytest.mark.integration
class TestSectorPerformance:

    def test_returns_all_sectors(self, av_api_key):
        result = get_sector_performance_alpha_vantage()
        assert isinstance(result, str)
        assert "Sector" in result
        assert "|" in result
        # Should contain at least some sector names
        assert any(s in result for s in ["Technology", "Healthcare", "Energy", "Financials"])


@pytest.mark.integration
class TestIndustryPerformance:

    def test_technology_sector(self, av_api_key):
        result = get_industry_performance_alpha_vantage("technology")
        assert isinstance(result, str)
        assert "|" in result
        # Should contain some tech tickers
        assert any(t in result for t in ["AAPL", "MSFT", "NVDA", "GOOGL"])

    def test_invalid_sector_raises(self, av_api_key):
        with pytest.raises(ValueError):
            get_industry_performance_alpha_vantage("nonexistent_sector")


@pytest.mark.integration
class TestTopicNews:

    def test_market_news(self, av_api_key):
        result = get_topic_news_alpha_vantage("market", limit=5)
        assert isinstance(result, str)
        assert "News" in result

    def test_technology_news(self, av_api_key):
        result = get_topic_news_alpha_vantage("technology", limit=3)
        assert isinstance(result, str)
        assert len(result) > 50  # Should have some content
