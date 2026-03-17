"""End-to-end tests for scanner tools functionality."""

import pytest
from tradingagents.agents.utils.scanner_tools import (
    get_market_movers,
    get_market_indices,
    get_sector_performance,
    get_industry_performance,
    get_topic_news,
)


def test_scanner_tools_imports():
    """Verify that all scanner tools can be imported."""
    from tradingagents.agents.utils.scanner_tools import (
        get_market_movers,
        get_market_indices,
        get_sector_performance,
        get_industry_performance,
        get_topic_news,
    )

    # Check that each tool exists (they are StructuredTool objects)
    assert get_market_movers is not None
    assert get_market_indices is not None
    assert get_sector_performance is not None
    assert get_industry_performance is not None
    assert get_topic_news is not None

    # Check that each tool has the expected docstring
    assert "market movers" in get_market_movers.description.lower() if get_market_movers.description else True
    assert "market indices" in get_market_indices.description.lower() if get_market_indices.description else True
    assert "sector performance" in get_sector_performance.description.lower() if get_sector_performance.description else True
    assert "industry" in get_industry_performance.description.lower() if get_industry_performance.description else True
    assert "news" in get_topic_news.description.lower() if get_topic_news.description else True


def test_market_movers():
    """Test market movers for all categories."""
    for category in ["day_gainers", "day_losers", "most_actives"]:
        result = get_market_movers.invoke({"category": category})
        assert isinstance(result, str), f"Result for {category} should be a string"
        # Check that it's not an error message
        assert not result.startswith("Error:"), f"Error in {category}: {result[:100]}"
        # Check for expected header
        assert "# Market Movers:" in result, f"Missing header in {category} result"


def test_market_indices():
    """Test market indices."""
    result = get_market_indices.invoke({})
    assert isinstance(result, str), "Market indices result should be a string"
    assert not result.startswith("Error:"), f"Error in market indices: {result[:100]}"
    assert "# Major Market Indices" in result, "Missing header in market indices result"


def test_sector_performance():
    """Test sector performance."""
    result = get_sector_performance.invoke({})
    assert isinstance(result, str), "Sector performance result should be a string"
    assert not result.startswith("Error:"), f"Error in sector performance: {result[:100]}"
    assert "# Sector Performance Overview" in result, "Missing header in sector performance result"


def test_industry_performance():
    """Test industry performance for technology sector."""
    result = get_industry_performance.invoke({"sector_key": "technology"})
    assert isinstance(result, str), "Industry performance result should be a string"
    assert not result.startswith("Error:"), f"Error in industry performance: {result[:100]}"
    assert "# Industry Performance: Technology" in result, "Missing header in industry performance result"


def test_topic_news():
    """Test topic news for market topic."""
    result = get_topic_news.invoke({"topic": "market", "limit": 5})
    assert isinstance(result, str), "Topic news result should be a string"
    assert not result.startswith("Error:"), f"Error in topic news: {result[:100]}"
    assert "# News for Topic: market" in result, "Missing header in topic news result"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])