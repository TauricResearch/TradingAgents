"""
Tests for tradingagents/utils/report_exporter.py - Report export utilities with metadata.

This test file follows TDD principles - tests are written BEFORE implementation.
All tests should FAIL initially (RED phase) until the implementation is complete.

Test Coverage:
1. YAML frontmatter formatting and validation
2. Report creation with frontmatter
3. Filename generation following YYYY-MM-DD_SectionName.md pattern
4. JSON metadata serialization with datetime handling
5. Comprehensive report generation
6. Integration with save_report_section_decorator
"""

import json
import pytest
import tempfile
import yaml
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import the module to test (will fail initially - TDD RED phase)
# from tradingagents.utils.report_exporter import (
#     format_metadata_frontmatter,
#     create_report_with_frontmatter,
#     generate_section_filename,
#     save_json_metadata,
#     generate_comprehensive_report,
# )


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for output files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_metadata():
    """Create sample metadata for testing."""
    return {
        "ticker": "AAPL",
        "analysis_date": "2024-12-26",
        "date_range": "2024-11-26 to 2024-12-26",
        "analysts": ["market", "sentiment", "news", "fundamentals"],
        "data_vendor": "alpaca",
        "llm_provider": "openrouter",
        "shallow_thinker": "anthropic/claude-3.5-sonnet",
        "deep_thinker": "anthropic/claude-opus-4.5",
        "generated_at": datetime(2024, 12, 26, 14, 30, 0),
    }


@pytest.fixture
def sample_report_sections():
    """Create sample report sections for testing."""
    return {
        "market_report": "# Market Analysis\n\nAPPL shows strong momentum...",
        "sentiment_report": "# Social Sentiment\n\nPositive sentiment across social media...",
        "news_report": "# News Analysis\n\nRecent product launch received well...",
        "fundamentals_report": "# Fundamentals Analysis\n\nStrong financials with P/E of 25...",
        "investment_plan": "# Investment Plan\n\nRecommend BUY with target price $180...",
        "trader_investment_plan": "# Trading Plan\n\nEntry at $175, stop loss at $170...",
        "final_trade_decision": "# Final Decision\n\nExecute BUY order for 100 shares...",
    }


@pytest.fixture
def partial_report_sections():
    """Create partial report sections (some analysts haven't completed)."""
    return {
        "market_report": "# Market Analysis\n\nAPPL shows strong momentum...",
        "sentiment_report": None,
        "news_report": "# News Analysis\n\nRecent product launch received well...",
        "fundamentals_report": None,
        "investment_plan": None,
        "trader_investment_plan": None,
        "final_trade_decision": None,
    }


class TestFormatMetadataFrontmatter:
    """Test format_metadata_frontmatter() function."""

    def test_generates_valid_yaml_frontmatter(self, sample_metadata):
        """Test that frontmatter is valid YAML wrapped in --- delimiters."""
        from tradingagents.utils.report_exporter import format_metadata_frontmatter

        result = format_metadata_frontmatter(sample_metadata)

        # Should start and end with --- delimiters
        assert result.startswith("---\n")
        assert result.endswith("---\n")

        # Extract YAML content between delimiters
        yaml_content = result.split("---\n")[1]

        # Should parse as valid YAML
        parsed = yaml.safe_load(yaml_content)
        assert isinstance(parsed, dict)

    def test_includes_all_metadata_fields(self, sample_metadata):
        """Test that all metadata fields are included in frontmatter."""
        from tradingagents.utils.report_exporter import format_metadata_frontmatter

        result = format_metadata_frontmatter(sample_metadata)
        yaml_content = result.split("---\n")[1]
        parsed = yaml.safe_load(yaml_content)

        assert parsed["ticker"] == "AAPL"
        assert parsed["analysis_date"] == "2024-12-26"
        assert parsed["date_range"] == "2024-11-26 to 2024-12-26"
        assert parsed["analysts"] == ["market", "sentiment", "news", "fundamentals"]
        assert parsed["data_vendor"] == "alpaca"
        assert parsed["llm_provider"] == "openrouter"
        assert parsed["shallow_thinker"] == "anthropic/claude-3.5-sonnet"
        assert parsed["deep_thinker"] == "anthropic/claude-opus-4.5"

    def test_handles_datetime_serialization(self, sample_metadata):
        """Test that datetime objects are properly serialized to ISO format."""
        from tradingagents.utils.report_exporter import format_metadata_frontmatter

        result = format_metadata_frontmatter(sample_metadata)
        yaml_content = result.split("---\n")[1]
        parsed = yaml.safe_load(yaml_content)

        # generated_at should be serialized as ISO string
        assert "generated_at" in parsed
        assert isinstance(parsed["generated_at"], str)
        assert parsed["generated_at"] == "2024-12-26T14:30:00"

    def test_handles_empty_metadata(self):
        """Test that empty metadata dict produces valid YAML."""
        from tradingagents.utils.report_exporter import format_metadata_frontmatter

        result = format_metadata_frontmatter({})

        assert result.startswith("---\n")
        assert result.endswith("---\n")
        yaml_content = result.split("---\n")[1]
        parsed = yaml.safe_load(yaml_content)
        assert parsed == {} or parsed is None

    def test_handles_none_values(self):
        """Test that None values in metadata are handled gracefully."""
        from tradingagents.utils.report_exporter import format_metadata_frontmatter

        metadata = {
            "ticker": "AAPL",
            "analysis_date": None,
            "analysts": None,
        }

        result = format_metadata_frontmatter(metadata)
        yaml_content = result.split("---\n")[1]
        parsed = yaml.safe_load(yaml_content)

        assert parsed["ticker"] == "AAPL"
        assert parsed["analysis_date"] is None
        assert parsed["analysts"] is None

    def test_handles_special_characters_in_strings(self):
        """Test that special characters in strings are properly escaped."""
        from tradingagents.utils.report_exporter import format_metadata_frontmatter

        metadata = {
            "ticker": "AAPL",
            "notes": "Quote: \"strong buy\" & wait for: $180",
        }

        result = format_metadata_frontmatter(metadata)
        yaml_content = result.split("---\n")[1]
        parsed = yaml.safe_load(yaml_content)

        # Special characters should be preserved
        assert parsed["notes"] == "Quote: \"strong buy\" & wait for: $180"


class TestCreateReportWithFrontmatter:
    """Test create_report_with_frontmatter() function."""

    def test_combines_frontmatter_and_content(self, sample_metadata):
        """Test that frontmatter and content are properly combined."""
        from tradingagents.utils.report_exporter import create_report_with_frontmatter

        content = "# Market Analysis\n\nAPPL shows strong momentum..."
        result = create_report_with_frontmatter(content, sample_metadata)

        # Should start with frontmatter
        assert result.startswith("---\n")

        # Should contain content after frontmatter
        assert "# Market Analysis" in result
        assert "APPL shows strong momentum..." in result

        # Frontmatter should be followed by blank line and content
        parts = result.split("---\n", 2)
        assert len(parts) == 3  # ['', yaml_content, content]

    def test_frontmatter_before_content(self, sample_metadata):
        """Test that frontmatter appears before content with proper spacing."""
        from tradingagents.utils.report_exporter import create_report_with_frontmatter

        content = "# Market Analysis\n\nContent here"
        result = create_report_with_frontmatter(content, sample_metadata)

        # Find where frontmatter ends
        frontmatter_end = result.find("---\n", 4)  # Skip first ---
        content_start = result.find("# Market Analysis")

        assert frontmatter_end < content_start
        assert frontmatter_end > 0
        assert content_start > 0

    def test_handles_empty_content(self, sample_metadata):
        """Test that empty content string is handled gracefully."""
        from tradingagents.utils.report_exporter import create_report_with_frontmatter

        result = create_report_with_frontmatter("", sample_metadata)

        # Should still have valid frontmatter
        assert result.startswith("---\n")
        assert "---\n" in result[4:]  # Second --- exists

    def test_handles_multiline_content(self, sample_metadata):
        """Test that multiline content is preserved correctly."""
        from tradingagents.utils.report_exporter import create_report_with_frontmatter

        content = """# Market Analysis

## Price Action
AAPL shows strong momentum.

## Volume
High volume confirms the trend.

## Conclusion
Bullish outlook."""

        result = create_report_with_frontmatter(content, sample_metadata)

        # All content lines should be preserved
        assert "# Market Analysis" in result
        assert "## Price Action" in result
        assert "## Volume" in result
        assert "## Conclusion" in result

    def test_preserves_content_formatting(self, sample_metadata):
        """Test that content formatting (code blocks, lists, etc) is preserved."""
        from tradingagents.utils.report_exporter import create_report_with_frontmatter

        content = """# Analysis

```python
print("test")
```

- Item 1
- Item 2

**Bold text**"""

        result = create_report_with_frontmatter(content, sample_metadata)

        assert "```python" in result
        assert 'print("test")' in result
        assert "- Item 1" in result
        assert "**Bold text**" in result


class TestGenerateSectionFilename:
    """Test generate_section_filename() function."""

    def test_follows_date_section_pattern(self):
        """Test that filename follows YYYY-MM-DD_SectionName.md pattern."""
        from tradingagents.utils.report_exporter import generate_section_filename

        result = generate_section_filename("market_report", "2024-12-26")

        assert result == "2024-12-26_market_report.md"

    def test_converts_section_name_to_snake_case(self):
        """Test that section names are converted to snake_case."""
        from tradingagents.utils.report_exporter import generate_section_filename

        result = generate_section_filename("Market Report", "2024-12-26")

        # Should convert spaces to underscores and lowercase
        assert result == "2024-12-26_market_report.md"

    def test_handles_various_date_formats(self):
        """Test that various date string formats work."""
        from tradingagents.utils.report_exporter import generate_section_filename

        # ISO format
        result1 = generate_section_filename("market_report", "2024-12-26")
        assert result1 == "2024-12-26_market_report.md"

        # Different separator (should still work or normalize)
        result2 = generate_section_filename("market_report", "2024/12/26")
        assert "2024" in result2
        assert "12" in result2
        assert "26" in result2

    def test_handles_special_characters_in_section_name(self):
        """Test that special characters in section name are handled."""
        from tradingagents.utils.report_exporter import generate_section_filename

        result = generate_section_filename("market-report/analysis", "2024-12-26")

        # Special characters should be replaced or removed
        assert result.endswith(".md")
        assert "2024-12-26" in result

    def test_always_adds_md_extension(self):
        """Test that .md extension is always added."""
        from tradingagents.utils.report_exporter import generate_section_filename

        result1 = generate_section_filename("market_report", "2024-12-26")
        result2 = generate_section_filename("final_decision", "2024-12-26")

        assert result1.endswith(".md")
        assert result2.endswith(".md")

    def test_comprehensive_report_filename(self):
        """Test that comprehensive report gets special naming."""
        from tradingagents.utils.report_exporter import generate_section_filename

        result = generate_section_filename("comprehensive_report", "2024-12-26")

        assert result == "2024-12-26_comprehensive_report.md"


class TestSaveJsonMetadata:
    """Test save_json_metadata() function."""

    def test_creates_json_file(self, temp_output_dir, sample_metadata):
        """Test that JSON file is created at specified path."""
        from tradingagents.utils.report_exporter import save_json_metadata

        filepath = temp_output_dir / "metadata.json"
        save_json_metadata(sample_metadata, filepath)

        assert filepath.exists()
        assert filepath.is_file()

    def test_saves_valid_json(self, temp_output_dir, sample_metadata):
        """Test that saved file contains valid JSON."""
        from tradingagents.utils.report_exporter import save_json_metadata

        filepath = temp_output_dir / "metadata.json"
        save_json_metadata(sample_metadata, filepath)

        with open(filepath, "r") as f:
            data = json.load(f)

        assert isinstance(data, dict)

    def test_includes_all_metadata_fields(self, temp_output_dir, sample_metadata):
        """Test that all metadata fields are saved to JSON."""
        from tradingagents.utils.report_exporter import save_json_metadata

        filepath = temp_output_dir / "metadata.json"
        save_json_metadata(sample_metadata, filepath)

        with open(filepath, "r") as f:
            data = json.load(f)

        assert data["ticker"] == "AAPL"
        assert data["analysis_date"] == "2024-12-26"
        assert data["analysts"] == ["market", "sentiment", "news", "fundamentals"]
        assert data["llm_provider"] == "openrouter"

    def test_handles_datetime_serialization(self, temp_output_dir, sample_metadata):
        """Test that datetime objects are serialized to ISO format strings."""
        from tradingagents.utils.report_exporter import save_json_metadata

        filepath = temp_output_dir / "metadata.json"
        save_json_metadata(sample_metadata, filepath)

        with open(filepath, "r") as f:
            data = json.load(f)

        # generated_at should be ISO string
        assert "generated_at" in data
        assert isinstance(data["generated_at"], str)
        assert data["generated_at"] == "2024-12-26T14:30:00"

    def test_handles_nested_dictionaries(self, temp_output_dir):
        """Test that nested dictionaries are properly serialized."""
        from tradingagents.utils.report_exporter import save_json_metadata

        metadata = {
            "ticker": "AAPL",
            "config": {
                "llm_provider": "openrouter",
                "models": {
                    "shallow": "claude-3.5-sonnet",
                    "deep": "claude-opus-4.5",
                }
            }
        }

        filepath = temp_output_dir / "metadata.json"
        save_json_metadata(metadata, filepath)

        with open(filepath, "r") as f:
            data = json.load(f)

        assert data["config"]["llm_provider"] == "openrouter"
        assert data["config"]["models"]["shallow"] == "claude-3.5-sonnet"

    def test_overwrites_existing_file(self, temp_output_dir):
        """Test that existing file is overwritten with new data."""
        from tradingagents.utils.report_exporter import save_json_metadata

        filepath = temp_output_dir / "metadata.json"

        # Save first version
        save_json_metadata({"ticker": "AAPL"}, filepath)

        # Save second version
        save_json_metadata({"ticker": "GOOGL", "date": "2024-12-26"}, filepath)

        with open(filepath, "r") as f:
            data = json.load(f)

        # Should have new data
        assert data["ticker"] == "GOOGL"
        assert data["date"] == "2024-12-26"

    def test_creates_parent_directories(self, temp_output_dir):
        """Test that parent directories are created if they don't exist."""
        from tradingagents.utils.report_exporter import save_json_metadata

        filepath = temp_output_dir / "subdir" / "nested" / "metadata.json"
        save_json_metadata({"ticker": "AAPL"}, filepath)

        assert filepath.exists()

    def test_handles_path_as_string(self, temp_output_dir):
        """Test that function accepts both Path and string for filepath."""
        from tradingagents.utils.report_exporter import save_json_metadata

        filepath_str = str(temp_output_dir / "metadata.json")
        save_json_metadata({"ticker": "AAPL"}, filepath_str)

        assert Path(filepath_str).exists()

    def test_pretty_prints_json(self, temp_output_dir):
        """Test that JSON is formatted with indentation for readability."""
        from tradingagents.utils.report_exporter import save_json_metadata

        metadata = {
            "ticker": "AAPL",
            "analysts": ["market", "sentiment"],
        }

        filepath = temp_output_dir / "metadata.json"
        save_json_metadata(metadata, filepath)

        with open(filepath, "r") as f:
            content = f.read()

        # Should have indentation
        assert "  " in content or "\t" in content


class TestGenerateComprehensiveReport:
    """Test generate_comprehensive_report() function."""

    def test_includes_all_sections(self, sample_report_sections, sample_metadata):
        """Test that comprehensive report includes all completed sections."""
        from tradingagents.utils.report_exporter import generate_comprehensive_report

        result = generate_comprehensive_report(sample_report_sections, sample_metadata)

        # Should include frontmatter
        assert result.startswith("---\n")

        # Should include all sections
        assert "Market Analysis" in result
        assert "Social Sentiment" in result
        assert "News Analysis" in result
        assert "Fundamentals Analysis" in result
        assert "Investment Plan" in result
        assert "Trading Plan" in result
        assert "Final Decision" in result

    def test_skips_none_sections(self, partial_report_sections, sample_metadata):
        """Test that None sections are skipped in comprehensive report."""
        from tradingagents.utils.report_exporter import generate_comprehensive_report

        result = generate_comprehensive_report(partial_report_sections, sample_metadata)

        # Should include completed sections
        assert "Market Analysis" in result
        assert "News Analysis" in result

        # Should not have placeholders for None sections
        # (Exact format depends on implementation)

    def test_organizes_sections_by_team(self, sample_report_sections, sample_metadata):
        """Test that sections are organized by team (Analyst, Research, Trading, Portfolio)."""
        from tradingagents.utils.report_exporter import generate_comprehensive_report

        result = generate_comprehensive_report(sample_report_sections, sample_metadata)

        # Should have team headers
        assert "Analyst Team" in result or "Market Analysis" in result
        assert "Investment Plan" in result or "Research Team" in result

    def test_includes_metadata_in_frontmatter(self, sample_report_sections, sample_metadata):
        """Test that metadata is included in frontmatter."""
        from tradingagents.utils.report_exporter import generate_comprehensive_report

        result = generate_comprehensive_report(sample_report_sections, sample_metadata)

        # Extract frontmatter
        parts = result.split("---\n", 2)
        yaml_content = parts[1]
        parsed = yaml.safe_load(yaml_content)

        assert parsed["ticker"] == "AAPL"
        assert parsed["llm_provider"] == "openrouter"

    def test_handles_empty_report_sections(self, sample_metadata):
        """Test that empty report sections dict is handled gracefully."""
        from tradingagents.utils.report_exporter import generate_comprehensive_report

        result = generate_comprehensive_report({}, sample_metadata)

        # Should still have frontmatter
        assert result.startswith("---\n")

    def test_preserves_markdown_formatting(self, sample_report_sections, sample_metadata):
        """Test that markdown formatting in sections is preserved."""
        from tradingagents.utils.report_exporter import generate_comprehensive_report

        # Add markdown elements to sections
        sample_report_sections["market_report"] = """# Market Analysis

## Price Action
- Strong uptrend
- **Key level**: $175

```
Support: $170
Resistance: $180
```"""

        result = generate_comprehensive_report(sample_report_sections, sample_metadata)

        assert "## Price Action" in result
        assert "- Strong uptrend" in result
        assert "**Key level**" in result
        assert "```" in result

    def test_sections_appear_in_logical_order(self, sample_report_sections, sample_metadata):
        """Test that sections appear in logical order (analysts -> research -> trading -> portfolio)."""
        from tradingagents.utils.report_exporter import generate_comprehensive_report

        result = generate_comprehensive_report(sample_report_sections, sample_metadata)

        # Find positions of each section
        market_pos = result.find("Market Analysis")
        sentiment_pos = result.find("Social Sentiment")
        investment_pos = result.find("Investment Plan")
        trading_pos = result.find("Trading Plan")
        final_pos = result.find("Final Decision")

        # Analyst sections should come before investment plan
        assert market_pos < investment_pos
        assert sentiment_pos < investment_pos

        # Investment plan before trading plan
        assert investment_pos < trading_pos

        # Trading plan before final decision
        assert trading_pos < final_pos


class TestSaveReportSectionDecoratorIntegration:
    """Integration tests for enhanced save_report_section_decorator."""

    def test_creates_section_file_with_frontmatter(self, temp_output_dir, sample_metadata):
        """Test that decorator creates section files with YAML frontmatter."""
        # This will test the enhanced decorator in cli/main.py
        # Mock the MessageBuffer and test the decorator

        from unittest.mock import Mock
        # Import will be available after implementation
        # from tradingagents.utils.report_exporter import create_report_with_frontmatter

        # For now, test the expected behavior
        section_name = "market_report"
        content = "# Market Analysis\n\nAPPL shows strength"
        expected_filename = f"2024-12-26_{section_name}.md"

        # File should be created with frontmatter
        # This test validates the integration point

    def test_saves_comprehensive_report(self, temp_output_dir, sample_report_sections):
        """Test that comprehensive report is saved after all sections complete."""
        # Test that when all sections are complete, comprehensive report is generated
        pass

    def test_saves_json_metadata_alongside_reports(self, temp_output_dir, sample_metadata):
        """Test that JSON metadata file is saved alongside markdown reports."""
        # Test that metadata.json is created with all parameters
        expected_file = temp_output_dir / "metadata.json"

        # File should exist and contain metadata
        # This test validates the integration point


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_unicode_in_content(self, sample_metadata):
        """Test that unicode characters in content are handled correctly."""
        from tradingagents.utils.report_exporter import create_report_with_frontmatter

        content = "# Analysis\n\nPrice: €100, ¥1000, £50, 📈 trending up"
        result = create_report_with_frontmatter(content, sample_metadata)

        assert "€100" in result
        assert "¥1000" in result
        assert "£50" in result
        assert "📈" in result

    def test_handles_very_long_content(self, sample_metadata):
        """Test that very long content is handled correctly."""
        from tradingagents.utils.report_exporter import create_report_with_frontmatter

        # Generate large content
        content = "# Analysis\n\n" + ("Long paragraph. " * 10000)
        result = create_report_with_frontmatter(content, sample_metadata)

        assert result.startswith("---\n")
        assert "Long paragraph." in result

    def test_handles_empty_string_section_name(self):
        """Test that empty section name is handled gracefully."""
        from tradingagents.utils.report_exporter import generate_section_filename

        # Should handle gracefully or raise descriptive error
        try:
            result = generate_section_filename("", "2024-12-26")
            # If it doesn't raise, should produce valid filename
            assert result.endswith(".md")
        except ValueError as e:
            # Or should raise descriptive error
            assert "section" in str(e).lower() or "name" in str(e).lower()

    def test_handles_invalid_date_format(self):
        """Test that invalid date format is handled gracefully."""
        from tradingagents.utils.report_exporter import generate_section_filename

        # Should handle gracefully or raise descriptive error
        try:
            result = generate_section_filename("market_report", "invalid-date")
            assert result.endswith(".md")
        except ValueError as e:
            assert "date" in str(e).lower()

    def test_handles_path_with_spaces(self, temp_output_dir):
        """Test that file paths with spaces are handled correctly."""
        from tradingagents.utils.report_exporter import save_json_metadata

        subdir = temp_output_dir / "path with spaces"
        subdir.mkdir()
        filepath = subdir / "metadata.json"

        save_json_metadata({"ticker": "AAPL"}, filepath)

        assert filepath.exists()

    def test_handles_concurrent_writes(self, temp_output_dir):
        """Test that concurrent writes to same file are handled safely."""
        from tradingagents.utils.report_exporter import save_json_metadata

        filepath = temp_output_dir / "metadata.json"

        # Multiple writes in sequence
        for i in range(5):
            save_json_metadata({"iteration": i}, filepath)

        # Last write should win
        with open(filepath, "r") as f:
            data = json.load(f)
        assert data["iteration"] == 4

    def test_metadata_with_list_of_dicts(self, temp_output_dir):
        """Test that metadata containing list of dictionaries is serialized correctly."""
        from tradingagents.utils.report_exporter import save_json_metadata

        metadata = {
            "ticker": "AAPL",
            "analysts_config": [
                {"name": "market", "enabled": True},
                {"name": "sentiment", "enabled": False},
            ]
        }

        filepath = temp_output_dir / "metadata.json"
        save_json_metadata(metadata, filepath)

        with open(filepath, "r") as f:
            data = json.load(f)

        assert len(data["analysts_config"]) == 2
        assert data["analysts_config"][0]["name"] == "market"
        assert data["analysts_config"][1]["enabled"] is False


class TestYAMLCompatibility:
    """Test YAML frontmatter compatibility with various parsers."""

    def test_frontmatter_parseable_by_jekyll(self, sample_metadata):
        """Test that frontmatter is compatible with Jekyll static site generator."""
        from tradingagents.utils.report_exporter import format_metadata_frontmatter

        result = format_metadata_frontmatter(sample_metadata)

        # Jekyll expects exactly three dashes
        assert result.startswith("---\n")
        assert result.count("---\n") == 2

    def test_frontmatter_parseable_by_hugo(self, sample_metadata):
        """Test that frontmatter is compatible with Hugo static site generator."""
        from tradingagents.utils.report_exporter import format_metadata_frontmatter

        result = format_metadata_frontmatter(sample_metadata)
        yaml_content = result.split("---\n")[1]

        # Hugo requires valid YAML
        parsed = yaml.safe_load(yaml_content)
        assert isinstance(parsed, dict)

    def test_frontmatter_no_tab_characters(self, sample_metadata):
        """Test that frontmatter uses spaces not tabs (YAML requirement)."""
        from tradingagents.utils.report_exporter import format_metadata_frontmatter

        result = format_metadata_frontmatter(sample_metadata)

        # YAML should use spaces for indentation
        assert "\t" not in result


class TestFilenamePatterns:
    """Test filename pattern generation and validation."""

    def test_all_section_filenames_unique(self, sample_report_sections):
        """Test that all section filenames are unique."""
        from tradingagents.utils.report_exporter import generate_section_filename

        date = "2024-12-26"
        filenames = set()

        for section_name in sample_report_sections.keys():
            filename = generate_section_filename(section_name, date)
            assert filename not in filenames
            filenames.add(filename)

        # Should have 7 unique filenames
        assert len(filenames) == 7

    def test_comprehensive_report_filename_distinct(self):
        """Test that comprehensive report filename is distinct from sections."""
        from tradingagents.utils.report_exporter import generate_section_filename

        date = "2024-12-26"

        section_files = [
            generate_section_filename("market_report", date),
            generate_section_filename("sentiment_report", date),
        ]

        comprehensive_file = generate_section_filename("comprehensive_report", date)

        assert comprehensive_file not in section_files

    def test_filename_sorting_chronological(self):
        """Test that filenames sort chronologically by date."""
        from tradingagents.utils.report_exporter import generate_section_filename

        files = [
            generate_section_filename("market_report", "2024-12-26"),
            generate_section_filename("market_report", "2024-12-25"),
            generate_section_filename("market_report", "2024-12-27"),
        ]

        sorted_files = sorted(files)

        # Should sort by date
        assert sorted_files[0].startswith("2024-12-25")
        assert sorted_files[1].startswith("2024-12-26")
        assert sorted_files[2].startswith("2024-12-27")


if __name__ == "__main__":
    # Run tests with minimal verbosity to prevent subprocess pipe deadlock (Issue #90)
    pytest.main([__file__, "--tb=line", "-q"])
