"""
Report export utilities with metadata.

This module provides functions for exporting trading analysis reports with YAML frontmatter
metadata and JSON sidecar files. It supports individual section reports and comprehensive
multi-section reports.

Features:
- YAML frontmatter formatting for markdown files
- Report creation with metadata
- Safe filename generation with date prefixes
- JSON metadata serialization with datetime handling
- Comprehensive report generation with table of contents

Usage:
    from tradingagents.utils.report_exporter import (
        create_report_with_frontmatter,
        generate_section_filename,
        save_json_metadata,
        generate_comprehensive_report
    )

    # Create single section report
    metadata = {
        "ticker": "AAPL",
        "analysis_date": "2024-12-26",
        "generated_at": datetime.now()
    }

    content = "# Market Analysis\\n\\nStrong momentum..."
    report = create_report_with_frontmatter(content, metadata)

    # Generate filename
    filename = generate_section_filename("market_report", "2024-12-26")

    # Save JSON metadata
    save_json_metadata(metadata, Path("output") / "metadata.json")

    # Create comprehensive report from multiple sections
    sections = {
        "market_report": "# Market Analysis\\n...",
        "sentiment_report": "# Sentiment\\n..."
    }
    comprehensive = generate_comprehensive_report(sections, metadata)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    import yaml
except ImportError:
    yaml = None

from tradingagents.utils.logging_config import setup_dual_logger

logger = setup_dual_logger(__name__)


def format_metadata_frontmatter(metadata: dict) -> str:
    """
    Format metadata dict as YAML frontmatter wrapped in --- delimiters.

    Converts metadata dictionary into YAML format suitable for markdown frontmatter.
    Handles datetime objects by converting them to ISO format strings. Sorts keys
    for consistency.

    Args:
        metadata: Dictionary containing metadata fields

    Returns:
        String containing YAML frontmatter wrapped in --- delimiters

    Example:
        >>> metadata = {"ticker": "AAPL", "date": "2024-12-26"}
        >>> frontmatter = format_metadata_frontmatter(metadata)
        >>> print(frontmatter)
        ---
        ticker: AAPL
        date: 2024-12-26
        ---
    """
    if yaml is None:
        logger.warning("PyYAML not installed - using basic YAML formatting")
        # Fallback to basic YAML formatting if pyyaml not available
        yaml_lines = []
        for key in sorted(metadata.keys()):
            value = metadata[key]
            if isinstance(value, datetime):
                value = value.isoformat()
            yaml_lines.append(f"{key}: {_format_yaml_value(value)}")
        yaml_content = "\n".join(yaml_lines)
    else:
        # Convert datetime objects to ISO format strings
        serializable_metadata = _convert_datetimes_to_iso(metadata)

        # Generate YAML with sorted keys
        yaml_content = yaml.safe_dump(
            serializable_metadata,
            default_flow_style=False,
            sort_keys=True,
            allow_unicode=True
        ).rstrip()

    # Wrap in frontmatter delimiters
    return f"---\n{yaml_content}\n---\n"


def create_report_with_frontmatter(content: str, metadata: dict) -> str:
    """
    Combine YAML frontmatter with markdown content.

    Creates a complete markdown report by prepending YAML frontmatter to the content.
    The frontmatter is separated from content by a blank line for readability.

    Args:
        content: Markdown content for the report
        metadata: Dictionary containing metadata fields

    Returns:
        String containing complete report with frontmatter and content

    Example:
        >>> content = "# Market Analysis\\n\\nStrong momentum"
        >>> metadata = {"ticker": "AAPL"}
        >>> report = create_report_with_frontmatter(content, metadata)
    """
    frontmatter = format_metadata_frontmatter(metadata)

    # Combine frontmatter and content with blank line separator
    return f"{frontmatter}\n{content}"


def generate_section_filename(section_name: str, date: str) -> str:
    """
    Generate safe filename from section name and date.

    Creates a filename following the pattern: YYYY-MM-DD_section_name.md
    Sanitizes special characters, converts to lowercase, and replaces spaces
    with underscores.

    Args:
        section_name: Name of the report section (e.g., "market_report")
        date: Date string in YYYY-MM-DD format (or similar formats)

    Returns:
        String containing safe filename with .md extension

    Raises:
        ValueError: If section_name is empty

    Example:
        >>> filename = generate_section_filename("Market Report", "2024-12-26")
        >>> print(filename)
        2024-12-26_market_report.md
    """
    if not section_name or not section_name.strip():
        raise ValueError("Section name cannot be empty")

    # Normalize date format - replace / with - if present
    normalized_date = date.replace("/", "-")

    # Sanitize section name:
    # 1. Convert to lowercase
    # 2. Replace spaces with underscores
    # 3. Remove or replace special characters
    sanitized_name = section_name.lower().strip()
    sanitized_name = sanitized_name.replace(" ", "_")

    # Remove or replace special characters (keep alphanumeric, underscore, hyphen)
    sanitized_name = re.sub(r'[^a-z0-9_-]', '_', sanitized_name)

    # Remove consecutive underscores
    sanitized_name = re.sub(r'_+', '_', sanitized_name)

    # Remove leading/trailing underscores
    sanitized_name = sanitized_name.strip('_')

    # Construct filename
    return f"{normalized_date}_{sanitized_name}.md"


def save_json_metadata(metadata: dict, filepath: Union[Path, str]) -> None:
    """
    Save metadata as JSON sidecar file.

    Serializes metadata dictionary to JSON with indentation for readability.
    Handles datetime objects by converting to ISO format strings. Creates
    parent directories if they don't exist.

    Args:
        metadata: Dictionary containing metadata fields
        filepath: Path where JSON file should be saved (Path or string)

    Returns:
        None. Creates a JSON file at the specified filepath with formatted metadata.

    Example:
        >>> metadata = {"ticker": "AAPL", "date": "2024-12-26"}
        >>> save_json_metadata(metadata, Path("output/metadata.json"))
    """
    # Convert to Path if string
    filepath = Path(filepath)

    # Create parent directories if needed
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Convert datetime objects to ISO format strings
    serializable_metadata = _convert_datetimes_to_iso(metadata)

    # Write JSON with indentation for readability
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(serializable_metadata, f, indent=2, ensure_ascii=False)

    logger.debug(f"Saved JSON metadata to {filepath}")


def generate_comprehensive_report(report_sections: dict, metadata: dict) -> str:
    """
    Combine all report sections into single comprehensive report.

    Creates a comprehensive markdown report by combining all completed sections
    in logical order (Analyst Team -> Research Team -> Trading Team -> Portfolio Team).
    Skips sections with None values. Includes YAML frontmatter with full metadata
    and a table of contents.

    Args:
        report_sections: Dictionary mapping section names to content (str or None)
        metadata: Dictionary containing metadata fields

    Returns:
        String containing comprehensive report with all sections

    Example:
        >>> sections = {
        ...     "market_report": "# Market Analysis\\n...",
        ...     "sentiment_report": "# Sentiment\\n...",
        ...     "investment_plan": "# Investment Plan\\n..."
        ... }
        >>> metadata = {"ticker": "AAPL", "date": "2024-12-26"}
        >>> report = generate_comprehensive_report(sections, metadata)
    """
    # Start with frontmatter
    frontmatter = format_metadata_frontmatter(metadata)

    # Define section order by team
    section_order = [
        # Analyst Team
        ("market_report", "Market Analysis"),
        ("sentiment_report", "Social Sentiment"),
        ("news_report", "News Analysis"),
        ("fundamentals_report", "Fundamentals Analysis"),
        # Research Team
        ("investment_plan", "Investment Plan"),
        # Trading Team
        ("trader_investment_plan", "Trading Plan"),
        # Portfolio Team
        ("final_trade_decision", "Final Decision"),
    ]

    # Collect completed sections
    completed_sections = []
    toc_entries = []

    for section_key, section_title in section_order:
        if section_key in report_sections and report_sections[section_key] is not None:
            content = report_sections[section_key].strip()
            if content:
                completed_sections.append(content)
                # Extract first heading for TOC if available
                if content.startswith("#"):
                    first_line = content.split("\n")[0]
                    toc_entries.append(first_line.replace("#", "").strip())
                else:
                    toc_entries.append(section_title)

    # Build comprehensive report
    report_parts = [frontmatter]

    # Add title
    ticker = metadata.get("ticker", "Unknown")
    date = metadata.get("analysis_date", "Unknown")
    report_parts.append(f"# Comprehensive Trading Analysis Report: {ticker}\n")
    report_parts.append(f"**Analysis Date**: {date}\n")

    # Add table of contents if there are sections
    if toc_entries:
        report_parts.append("## Table of Contents\n")
        for i, entry in enumerate(toc_entries, 1):
            report_parts.append(f"{i}. {entry}")
        report_parts.append("\n---\n")

    # Add team headers and sections in logical order
    current_team = None
    team_mapping = {
        "market_report": "Analyst Team",
        "sentiment_report": "Analyst Team",
        "news_report": "Analyst Team",
        "fundamentals_report": "Analyst Team",
        "investment_plan": "Research Team",
        "trader_investment_plan": "Trading Team",
        "final_trade_decision": "Portfolio Team",
    }

    for section_key, section_title in section_order:
        if section_key in report_sections and report_sections[section_key] is not None:
            content = report_sections[section_key].strip()
            if content:
                # Add team header if this is a new team
                team = team_mapping.get(section_key)
                if team and team != current_team:
                    report_parts.append(f"\n## {team}\n")
                    current_team = team

                # Add section content
                report_parts.append(f"\n{content}\n")

    return "\n".join(report_parts)


# Helper functions

def _convert_datetimes_to_iso(obj: Any) -> Any:
    """
    Recursively convert datetime objects to ISO format strings.

    Args:
        obj: Object to convert (can be dict, list, datetime, or other)

    Returns:
        Converted object with datetimes as ISO strings
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: _convert_datetimes_to_iso(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_convert_datetimes_to_iso(item) for item in obj]
    else:
        return obj


def _format_yaml_value(value: Any) -> str:
    """
    Format a value for basic YAML output (fallback when pyyaml not available).

    Args:
        value: Value to format

    Returns:
        String representation suitable for YAML
    """
    if value is None:
        return "null"
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (list, tuple)):
        items = ", ".join(_format_yaml_value(item) for item in value)
        return f"[{items}]"
    elif isinstance(value, dict):
        # Simple dict formatting - not perfect but works for basic cases
        items = ", ".join(f"{k}: {_format_yaml_value(v)}" for k, v in value.items())
        return f"{{{items}}}"
    elif isinstance(value, str):
        # Quote strings with special characters
        if any(char in value for char in [':', '{', '}', '[', ']', ',', '&', '*', '#', '?', '|', '-', '<', '>', '=', '!', '%', '@', '\\']):
            return f'"{value}"'
        return value
    else:
        return str(value)
