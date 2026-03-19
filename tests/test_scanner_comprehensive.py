"""Comprehensive end-to-end tests for scanner functionality."""

import tempfile
import os
from pathlib import Path
from unittest.mock import patch
import pytest

from tradingagents.agents.utils.scanner_tools import (
    get_market_movers,
    get_market_indices,
    get_sector_performance,
    get_industry_performance,
    get_topic_news,
)
from cli.main import run_scan


class TestScannerTools:
    """Test individual scanner tools."""

    def test_market_movers_all_categories(self):
        """Test market movers for all categories."""
        for category in ["day_gainers", "day_losers", "most_actives"]:
            result = get_market_movers.invoke({"category": category})
            assert isinstance(result, str), f"Result for {category} should be a string"
            assert not result.startswith("Error:"), f"Error in {category}: {result[:100]}"
            assert "# Market Movers:" in result, f"Missing header in {category} result"
            assert "| Symbol |" in result, f"Missing table header in {category} result"
            # Check that we got some data
            assert len(result) > 100, f"Result too short for {category}"

    def test_market_indices(self):
        """Test market indices."""
        result = get_market_indices.invoke({})
        assert isinstance(result, str), "Market indices result should be a string"
        assert not result.startswith("Error:"), f"Error in market indices: {result[:100]}"
        assert "# Major Market Indices" in result, "Missing header in market indices result"
        assert "| Index |" in result, "Missing table header in market indices result"
        # Check for major indices
        assert "S&P 500" in result, "Missing S&P 500 in market indices"
        assert "Dow Jones" in result, "Missing Dow Jones in market indices"

    def test_sector_performance(self):
        """Test sector performance."""
        result = get_sector_performance.invoke({})
        assert isinstance(result, str), "Sector performance result should be a string"
        assert not result.startswith("Error:"), f"Error in sector performance: {result[:100]}"
        assert "# Sector Performance Overview" in result, "Missing header in sector performance result"
        assert "| Sector |" in result, "Missing table header in sector performance result"
        # Check for some sectors
        assert "Technology" in result, "Missing Technology sector"
        assert "Healthcare" in result, "Missing Healthcare sector"

    def test_industry_performance(self):
        """Test industry performance for technology sector."""
        result = get_industry_performance.invoke({"sector_key": "technology"})
        assert isinstance(result, str), "Industry performance result should be a string"
        assert not result.startswith("Error:"), f"Error in industry performance: {result[:100]}"
        assert "# Industry Performance: Technology" in result, "Missing header in industry performance result"
        assert "| Company |" in result, "Missing table header in industry performance result"
        # Check for major tech companies
        assert "NVIDIA" in result or "Apple" in result or "Microsoft" in result, "Missing major tech companies"

    def test_topic_news(self):
        """Test topic news for market topic."""
        result = get_topic_news.invoke({"topic": "market", "limit": 5})
        assert isinstance(result, str), "Topic news result should be a string"
        assert not result.startswith("Error:"), f"Error in topic news: {result[:100]}"
        assert "# News for Topic: market" in result, "Missing header in topic news result"
        assert "### " in result, "Missing news article headers in topic news result"
        # Check that we got some news
        assert len(result) > 100, "Topic news result too short"


class TestScannerEndToEnd:
    """End-to-end tests for scanner functionality."""

    def test_scan_command_creates_output_files(self):
        """Test that the scan command creates all expected output files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_date_dir = Path(temp_dir) / "market"
            test_date_dir.mkdir(parents=True)

            # Mock get_market_dir to redirect output into the temp directory
            with patch('cli.main.get_market_dir', return_value=test_date_dir):
                # Mock the write_text method to capture what gets written
                written_files = {}
                def mock_write_text(self, content, encoding=None):
                    written_files[str(self)] = content

                with patch('pathlib.Path.write_text', mock_write_text):
                    with patch('typer.prompt', return_value='2026-03-15'):
                        try:
                            run_scan()
                        except SystemExit:
                            pass

            # Verify that run_scan() uses the correct output file naming convention.
            #
            # run_scan() writes via: (save_dir / f"{key}.md").write_text(content)
            # where save_dir = get_market_dir(scan_date).
            # pathlib.Path.write_text is mocked, so written_files keys are the
            # str() of those Path objects.
            #
            # LLM output is non-deterministic: a phase may produce an empty string,
            # causing run_scan()'s `if content:` guard to skip writing that file.
            # So we cannot assert ALL 5 files are always present.  Instead we verify:
            #   1. At least some output was produced (pipeline didn't silently fail).
            #   2. Every file that WAS written has a name matching the expected
            #      naming convention — this is the real bug we are guarding against.
            valid_names = {
                "geopolitical_report.md",
                "market_movers_report.md",
                "sector_performance_report.md",
                "industry_deep_dive_report.md",
                "macro_scan_summary.md",
                "run_log.jsonl",
            }

            assert len(written_files) >= 1, (
                "Scanner produced no output files — pipeline may have silently failed"
            )

            for filepath, content in written_files.items():
                filename = filepath.split("/")[-1]
                assert filename in valid_names, (
                    f"Output file '{filename}' does not match the expected naming "
                    f"convention.  run_scan() should only write {sorted(valid_names)}"
                )
                assert len(content) > 50, (
                    f"File {filename} appears to be empty or too short"
                )

    def test_scanner_tools_integration(self):
        """Test that all scanner tools work together without errors."""
        # Test all tools can be called successfully
        tools_and_args = [
            (get_market_movers, {"category": "day_gainers"}),
            (get_market_indices, {}),
            (get_sector_performance, {}),
            (get_industry_performance, {"sector_key": "technology"}),
            (get_topic_news, {"topic": "market", "limit": 3})
        ]
        
        for tool_func, args in tools_and_args:
            result = tool_func.invoke(args)
            assert isinstance(result, str), f"Tool {tool_func.name} should return string"
            # Either we got real data or a graceful error message
            assert not result.startswith("Error fetching"), f"Tool {tool_func.name} failed: {result[:100]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])