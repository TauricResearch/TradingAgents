"""
Test Twitter integration in Discovery Graph.

This test verifies that the scanner_node correctly processes Twitter data
and adds candidates with source="twitter_sentiment".
"""

import pytest
from unittest.mock import patch, MagicMock
from tradingagents.graph.discovery_graph import DiscoveryGraph
from tradingagents.agents.utils.agent_states import DiscoveryState


@pytest.fixture
def mock_config():
    """Mock configuration for DiscoveryGraph."""
    return {
        "llm_provider": "openai",
        "deep_think_llm": "gpt-4",
        "quick_think_llm": "gpt-3.5-turbo",
        "backend_url": "https://api.openai.com/v1",
        "discovery": {
            "reddit_trending_limit": 15,
            "market_movers_limit": 10,
            "max_candidates_to_analyze": 10,
            "news_lookback_days": 7,
            "final_recommendations": 3
        }
    }


@pytest.fixture
def discovery_graph(mock_config):
    """Create a DiscoveryGraph instance with mocked config."""
    with patch('langchain_openai.ChatOpenAI'):
        graph = DiscoveryGraph(config=mock_config)
        return graph


def test_scanner_node_twitter_integration(discovery_graph):
    """Test that scanner_node processes Twitter data correctly."""
    
    # Mock the execute_tool function
    with patch('tradingagents.graph.discovery_graph.execute_tool') as mock_execute_tool:
        # Mock Twitter response
        fake_tweets = """
        Tweet 1: $AAPL is looking strong! Great earnings report.
        Tweet 2: Watching $TSLA closely, could be a good entry point.
        Tweet 3: $NVDA continues to dominate AI chip market.
        """
        
        # Mock LLM response for ticker extraction
        mock_llm_response = MagicMock()
        mock_llm_response.content = "AAPL, TSLA, NVDA"
        
        # Setup mock returns
        def execute_tool_side_effect(tool_name, **kwargs):
            if tool_name == "get_tweets":
                return fake_tweets
            elif tool_name == "validate_ticker":
                # All tickers are valid
                return True
            elif tool_name == "get_trending_tickers":
                return "Reddit trending: GME, AMC"
            elif tool_name == "get_market_movers":
                return "Gainers: MSFT, Losers: META"
            return ""
        
        mock_execute_tool.side_effect = execute_tool_side_effect
        
        # Mock the LLM
        discovery_graph.quick_thinking_llm.invoke = MagicMock(return_value=mock_llm_response)
        
        # Run scanner_node
        initial_state = DiscoveryState()
        result = discovery_graph.scanner_node(initial_state)
        
        # Verify results
        assert "candidate_metadata" in result
        candidates = result["candidate_metadata"]
        
        # Check that Twitter candidates were added
        twitter_candidates = [c for c in candidates if c["source"] == "twitter_sentiment"]
        assert len(twitter_candidates) > 0, "No Twitter candidates found"
        
        # Verify Twitter tickers are present
        twitter_tickers = [c["ticker"] for c in twitter_candidates]
        assert "AAPL" in twitter_tickers or "TSLA" in twitter_tickers or "NVDA" in twitter_tickers
        
        # Verify execute_tool was called with correct parameters
        mock_execute_tool.assert_any_call("get_tweets", query="stocks to watch", count=20)
        
        print(f"✅ Test passed! Found {len(twitter_candidates)} Twitter candidates: {twitter_tickers}")


def test_scanner_node_twitter_validation(discovery_graph):
    """Test that invalid tickers are filtered out."""
    
    with patch('tradingagents.graph.discovery_graph.execute_tool') as mock_execute_tool:
        # Mock Twitter response with invalid tickers
        fake_tweets = "Check out $AAPL and $INVALID and $BTC"
        
        # Mock LLM response
        mock_llm_response = MagicMock()
        mock_llm_response.content = "AAPL, INVALID, BTC"
        
        # Setup mock returns - only AAPL is valid
        def execute_tool_side_effect(tool_name, **kwargs):
            if tool_name == "get_tweets":
                return fake_tweets
            elif tool_name == "validate_ticker":
                symbol = kwargs.get("symbol", "")
                return symbol == "AAPL"  # Only AAPL is valid
            elif tool_name == "get_trending_tickers":
                return ""
            elif tool_name == "get_market_movers":
                return ""
            return ""
        
        mock_execute_tool.side_effect = execute_tool_side_effect
        discovery_graph.quick_thinking_llm.invoke = MagicMock(return_value=mock_llm_response)
        
        # Run scanner_node
        initial_state = DiscoveryState()
        result = discovery_graph.scanner_node(initial_state)
        
        # Verify only valid tickers were added
        candidates = result["candidate_metadata"]
        twitter_candidates = [c for c in candidates if c["source"] == "twitter_sentiment"]
        twitter_tickers = [c["ticker"] for c in twitter_candidates]
        
        assert "AAPL" in twitter_tickers, "Valid ticker AAPL should be present"
        assert "INVALID" not in twitter_tickers, "Invalid ticker should be filtered out"
        assert "BTC" not in twitter_tickers, "Crypto ticker should be filtered out"
        
        print(f"✅ Validation test passed! Only valid tickers: {twitter_tickers}")


def test_scanner_node_twitter_error_handling(discovery_graph):
    """Test that scanner_node handles Twitter API errors gracefully."""
    
    with patch('tradingagents.graph.discovery_graph.execute_tool') as mock_execute_tool:
        # Mock Twitter to raise an error
        def execute_tool_side_effect(tool_name, **kwargs):
            if tool_name == "get_tweets":
                raise Exception("Twitter API rate limit exceeded")
            elif tool_name == "get_trending_tickers":
                return "GME, AMC"
            elif tool_name == "get_market_movers":
                return "Gainers: MSFT"
            return ""
        
        mock_execute_tool.side_effect = execute_tool_side_effect
        
        # Mock LLM for Reddit
        mock_llm_response = MagicMock()
        mock_llm_response.content = "GME, AMC, MSFT"
        discovery_graph.quick_thinking_llm.invoke = MagicMock(return_value=mock_llm_response)
        
        # Run scanner_node - should not crash
        initial_state = DiscoveryState()
        result = discovery_graph.scanner_node(initial_state)
        
        # Should still have candidates from other sources
        assert "candidate_metadata" in result
        candidates = result["candidate_metadata"]
        assert len(candidates) > 0, "Should have candidates from other sources"
        
        # Should not have Twitter candidates
        twitter_candidates = [c for c in candidates if c["source"] == "twitter_sentiment"]
        assert len(twitter_candidates) == 0, "Should have no Twitter candidates due to error"
        
        print("✅ Error handling test passed! Graph continues despite Twitter error")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
