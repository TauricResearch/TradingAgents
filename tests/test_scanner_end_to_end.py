"""End-to-end tests for scanner functionality."""

import pytest

from tradingagents.agents.utils.scanner_tools import (
    get_market_movers,
    get_market_indices,
    get_sector_performance,
    get_industry_performance,
    get_topic_news,
)


def test_scanner_tools_end_to_end():
    """End-to-end test for all scanner tools."""
    # Test market movers
    for category in ["day_gainers", "day_losers", "most_actives"]:
        result = get_market_movers.invoke({"category": category})
        assert isinstance(result, str), f"Result for {category} should be a string"
        assert not result.startswith("Error:"), f"Error in {category}: {result[:100]}"
        assert "# Market Movers:" in result, f"Missing header in {category} result"
        assert "| Symbol |" in result, f"Missing table header in {category} result"

    # Test market indices
    result = get_market_indices.invoke({})
    assert isinstance(result, str), "Market indices result should be a string"
    assert not result.startswith("Error:"), f"Error in market indices: {result[:100]}"
    assert "# Major Market Indices" in result, "Missing header in market indices result"
    assert "| Index |" in result, "Missing table header in market indices result"

    # Test sector performance
    result = get_sector_performance.invoke({})
    assert isinstance(result, str), "Sector performance result should be a string"
    assert not result.startswith("Error:"), f"Error in sector performance: {result[:100]}"
    assert "# Sector Performance Overview" in result, "Missing header in sector performance result"
    assert "| Sector |" in result, "Missing table header in sector performance result"

    # Test industry performance
    result = get_industry_performance.invoke({"sector_key": "technology"})
    assert isinstance(result, str), "Industry performance result should be a string"
    assert not result.startswith("Error:"), f"Error in industry performance: {result[:100]}"
    assert "# Industry Performance: Technology" in result, "Missing header in industry performance result"
    assert "| Company |" in result, "Missing table header in industry performance result"

    # Test topic news
    result = get_topic_news.invoke({"topic": "market", "limit": 5})
    assert isinstance(result, str), "Topic news result should be a string"
    assert not result.startswith("Error:"), f"Error in topic news: {result[:100]}"
    assert "# News for Topic: market" in result, "Missing header in topic news result"
    assert "### " in result, "Missing news article headers in topic news result"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])