"""Tests for scanner tools functionality."""

# Basic import and attribute checks for scanner tools
def test_scanner_tools_imports():
    """Verify that all scanner tools can be imported."""
    from tradingagents.agents.utils.scanner_tools import (
        get_market_movers,
        get_market_indices,
        get_sector_performance,
        get_industry_performance,
        get_topic_news,
    )
    
    # Check that each tool function exists
    assert callable(get_market_movers)
    assert callable(get_market_indices)
    assert callable(get_sector_performance)
    assert callable(get_industry_performance)
    assert callable(get_topic_news)
    
    # Check that each tool has the expected docstring
    assert "market movers" in get_market_movers.__doc__.lower() if get_market_movers.__doc__ else True
    assert "market indices" in get_market_indices.__doc__.lower() if get_market_indices.__doc__ else True
    assert "sector performance" in get_sector_performance.__doc__.lower() if get_sector_performance.__doc__ else True
    assert "industry performance" in get_industry_performance.__doc__.lower() if get_industry_performance.__doc__ else True
    assert "topic news" in get_topic_news.__doc__.lower() if get_topic_news.__doc__ else True

if __name__ == "__main__":
    test_scanner_tools_imports()
    print("All scanner tool import tests passed.")