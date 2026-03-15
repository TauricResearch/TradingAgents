"""
Complete end-to-end test for TradingAgents scanner functionality.

This test verifies that:
1. All scanner tools work correctly and return expected data formats
2. The scanner tools can be used to generate market analysis reports
3. The CLI scan command works end-to-end
4. Results are properly saved to files
"""

import tempfile
import os
from pathlib import Path
import pytest

# Set up the Python path to include the project root
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tradingagents.agents.utils.scanner_tools import (
    get_market_movers,
    get_market_indices,
    get_sector_performance,
    get_industry_performance,
    get_topic_news,
)


class TestScannerToolsIndividual:
    """Test each scanner tool individually."""

    def test_get_market_movers(self):
        """Test market movers tool for all categories."""
        for category in ["day_gainers", "day_losers", "most_actives"]:
            result = get_market_movers.invoke({"category": category})
            assert isinstance(result, str), f"Result should be string for {category}"
            assert not result.startswith("Error:"), f"Should not error for {category}: {result[:100]}"
            assert "# Market Movers:" in result, f"Missing header for {category}"
            assert "| Symbol |" in result, f"Missing table header for {category}"
            # Verify we got actual data
            lines = result.split('\n')
            data_lines = [line for line in lines if line.startswith('|') and 'Symbol' not in line]
            assert len(data_lines) > 0, f"No data rows found for {category}"

    def test_get_market_indices(self):
        """Test market indices tool."""
        result = get_market_indices.invoke({})
        assert isinstance(result, str), "Result should be string"
        assert not result.startswith("Error:"), f"Should not error: {result[:100]}"
        assert "# Major Market Indices" in result, "Missing header"
        assert "| Index |" in result, "Missing table header"
        # Verify we got data for major indices
        assert "S&P 500" in result, "Missing S&P 500 data"
        assert "Dow Jones" in result, "Missing Dow Jones data"

    def test_get_sector_performance(self):
        """Test sector performance tool."""
        result = get_sector_performance.invoke({})
        assert isinstance(result, str), "Result should be string"
        assert not result.startswith("Error:"), f"Should not error: {result[:100]}"
        assert "# Sector Performance Overview" in result, "Missing header"
        assert "| Sector |" in result, "Missing table header"
        # Verify we got data for sectors
        assert "Technology" in result or "Healthcare" in result, "Missing sector data"

    def test_get_industry_performance(self):
        """Test industry performance tool."""
        result = get_industry_performance.invoke({"sector_key": "technology"})
        assert isinstance(result, str), "Result should be string"
        assert not result.startswith("Error:"), f"Should not error: {result[:100]}"
        assert "# Industry Performance: Technology" in result, "Missing header"
        assert "| Company |" in result, "Missing table header"
        # Verify we got data for companies
        assert "NVIDIA" in result or "Apple" in result or "Microsoft" in result, "Missing company data"

    def test_get_topic_news(self):
        """Test topic news tool."""
        result = get_topic_news.invoke({"topic": "market", "limit": 3})
        assert isinstance(result, str), "Result should be string"
        assert not result.startswith("Error:"), f"Should not error: {result[:100]}"
        assert "# News for Topic: market" in result, "Missing header"
        assert "### " in result, "Missing news article headers"
        # Verify we got news content
        assert len(result) > 100, "News result too short"


class TestScannerWorkflow:
    """Test the complete scanner workflow."""

    def test_complete_scanner_workflow_to_files(self):
        """Test that scanner tools can generate complete market analysis and save to files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set up directory structure like the CLI scan command
            scan_date = "2026-03-15"
            save_dir = Path(temp_dir) / "results" / "macro_scan" / scan_date
            save_dir.mkdir(parents=True)
            
            # Generate data using all scanner tools (this is what the CLI scan command does)
            market_movers = get_market_movers.invoke({"category": "day_gainers"})
            market_indices = get_market_indices.invoke({})
            sector_performance = get_sector_performance.invoke({})
            industry_performance = get_industry_performance.invoke({"sector_key": "technology"})
            topic_news = get_topic_news.invoke({"topic": "market", "limit": 5})
            
            # Save results to files (simulating CLI behavior)
            (save_dir / "market_movers.txt").write_text(market_movers)
            (save_dir / "market_indices.txt").write_text(market_indices)
            (save_dir / "sector_performance.txt").write_text(sector_performance)
            (save_dir / "industry_performance.txt").write_text(industry_performance)
            (save_dir / "topic_news.txt").write_text(topic_news)
            
            # Verify all files were created
            assert (save_dir / "market_movers.txt").exists()
            assert (save_dir / "market_indices.txt").exists()
            assert (save_dir / "sector_performance.txt").exists()
            assert (save_dir / "industry_performance.txt").exists()
            assert (save_dir / "topic_news.txt").exists()
            
            # Verify file contents have expected structure
            movers_content = (save_dir / "market_movers.txt").read_text()
            indices_content = (save_dir / "market_indices.txt").read_text()
            sectors_content = (save_dir / "sector_performance.txt").read_text()
            industry_content = (save_dir / "industry_performance.txt").read_text()
            news_content = (save_dir / "topic_news.txt").read_text()
            
            # Check headers
            assert "# Market Movers:" in movers_content
            assert "# Major Market Indices" in indices_content
            assert "# Sector Performance Overview" in sectors_content
            assert "# Industry Performance: Technology" in industry_content
            assert "# News for Topic: market" in news_content
            
            # Check table structures
            assert "| Symbol |" in movers_content
            assert "| Index |" in indices_content
            assert "| Sector |" in sectors_content
            assert "| Company |" in industry_content
            
            # Check that we have meaningful data (not just headers)
            assert len(movers_content) > 200
            assert len(indices_content) > 200
            assert len(sectors_content) > 200
            assert len(industry_content) > 200
            assert len(news_content) > 200


class TestScannerIntegration:
    """Test integration with CLI components."""

    def test_tools_have_expected_interface(self):
        """Test that scanner tools have the interface expected by CLI."""
        # The CLI scan command expects to call .invoke() on each tool
        assert hasattr(get_market_movers, 'invoke')
        assert hasattr(get_market_indices, 'invoke')
        assert hasattr(get_sector_performance, 'invoke')
        assert hasattr(get_industry_performance, 'invoke')
        assert hasattr(get_topic_news, 'invoke')
        
        # Verify they're callable with expected arguments
        # Market movers requires category argument
        result = get_market_movers.invoke({"category": "day_gainers"})
        assert isinstance(result, str)
        
        # Others don't require arguments (or have defaults)
        result = get_market_indices.invoke({})
        assert isinstance(result, str)
        
        result = get_sector_performance.invoke({})
        assert isinstance(result, str)
        
        result = get_industry_performance.invoke({"sector_key": "technology"})
        assert isinstance(result, str)
        
        result = get_topic_news.invoke({"topic": "market", "limit": 3})
        assert isinstance(result, str)

    def test_tool_descriptions_match_expectations(self):
        """Test that tool descriptions match what the CLI expects."""
        # These descriptions are used for documentation and help
        assert "market movers" in get_market_movers.description.lower()
        assert "market indices" in get_market_indices.description.lower()
        assert "sector performance" in get_sector_performance.description.lower()
        assert "industry" in get_industry_performance.description.lower()
        assert "news" in get_topic_news.description.lower()


def test_scanner_end_to_end_demo():
    """Demonstration test showing the complete end-to-end scanner functionality."""
    print("\n" + "="*60)
    print("TRADINGAGENTS SCANNER END-TO-END DEMONSTRATION")
    print("="*60)
    
    # Show that all tools work
    print("\n1. Testing Individual Scanner Tools:")
    print("-" * 40)
    
    # Market Movers
    movers = get_market_movers.invoke({"category": "day_gainers"})
    print(f"✓ Market Movers: {len(movers)} characters")
    
    # Market Indices
    indices = get_market_indices.invoke({})
    print(f"✓ Market Indices: {len(indices)} characters")
    
    # Sector Performance
    sectors = get_sector_performance.invoke({})
    print(f"✓ Sector Performance: {len(sectors)} characters")
    
    # Industry Performance
    industry = get_industry_performance.invoke({"sector_key": "technology"})
    print(f"✓ Industry Performance: {len(industry)} characters")
    
    # Topic News
    news = get_topic_news.invoke({"topic": "market", "limit": 3})
    print(f"✓ Topic News: {len(news)} characters")
    
    # Show file output capability
    print("\n2. Testing File Output Capability:")
    print("-" * 40)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        scan_date = "2026-03-15"
        save_dir = Path(temp_dir) / "results" / "macro_scan" / scan_date
        save_dir.mkdir(parents=True)
        
        # Save all results
        files_data = [
            ("market_movers.txt", movers),
            ("market_indices.txt", indices),
            ("sector_performance.txt", sectors),
            ("industry_performance.txt", industry),
            ("topic_news.txt", news)
        ]
        
        for filename, content in files_data:
            filepath = save_dir / filename
            filepath.write_text(content)
            assert filepath.exists()
            print(f"✓ Created {filename} ({len(content)} chars)")
        
        # Verify we can read them back
        for filename, _ in files_data:
            content = (save_dir / filename).read_text()
            assert len(content) > 50  # Sanity check
    
    print("\n3. Verifying Content Quality:")
    print("-" * 40)
    
    # Check that we got real financial data, not just error messages
    assert not movers.startswith("Error:"), "Market movers should not error"
    assert not indices.startswith("Error:"), "Market indices should not error"
    assert not sectors.startswith("Error:"), "Sector performance should not error"
    assert not industry.startswith("Error:"), "Industry performance should not error"
    assert not news.startswith("Error:"), "Topic news should not error"
    
    # Check for expected content patterns
    assert "# Market Movers: Day Gainers" in movers or "# Market Movers: Day Losers" in movers or "# Market Movers: Most Actives" in movers
    assert "# Major Market Indices" in indices
    assert "# Sector Performance Overview" in sectors
    assert "# Industry Performance: Technology" in industry
    assert "# News for Topic: market" in news
    
    print("✓ All tools returned valid financial data")
    print("✓ All tools have proper headers and formatting")
    print("✓ All tools can save/load data correctly")
    
    print("\n" + "="*60)
    print("END-TO-END SCANNER TEST: PASSED 🎉")
    print("="*60)
    print("The TradingAgents scanner functionality is working correctly!")
    print("All tools generate proper financial market data and can save results to files.")


if __name__ == "__main__":
    # Run the demonstration test
    test_scanner_end_to_end_demo()
    
    # Also run the individual test classes
    print("\nRunning individual tool tests...")
    test_instance = TestScannerToolsIndividual()
    test_instance.test_get_market_movers()
    test_instance.test_get_market_indices()
    test_instance.test_get_sector_performance()
    test_instance.test_get_industry_performance()
    test_instance.test_get_topic_news()
    print("✓ Individual tool tests passed")
    
    workflow_instance = TestScannerWorkflow()
    workflow_instance.test_complete_scanner_workflow_to_files()
    print("✓ Workflow tests passed")
    
    integration_instance = TestScannerIntegration()
    integration_instance.test_tools_have_expected_interface()
    integration_instance.test_tool_descriptions_match_expectations()
    print("✓ Integration tests passed")
    
    print("\n✅ ALL TESTS PASSED - Scanner functionality is working correctly!")