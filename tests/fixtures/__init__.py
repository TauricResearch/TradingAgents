"""
Test fixtures module providing mock data for TradingAgents tests.

This module provides a centralized FixtureLoader class for loading JSON-based
test fixtures including stock data, metadata, report sections, API responses,
and configurations. All datetime values are automatically parsed from ISO 8601
format strings.

Features:
- JSON file loading with automatic datetime parsing
- DataFrame conversion for stock data
- Specialized loaders for different fixture types
- UTF-8 encoding support for Chinese market data
- Edge case handling for robust testing

Usage:
    from tests.fixtures import FixtureLoader

    # Load stock data as DataFrame
    us_data = FixtureLoader.load_us_stock_data()
    cn_data = FixtureLoader.load_cn_stock_data()

    # Load metadata
    metadata = FixtureLoader.load_analysis_metadata("complete_analysis")

    # Load report sections
    reports = FixtureLoader.load_complete_report_sections()

    # Load API responses
    embedding = FixtureLoader.load_embedding_response()

    # Load configuration
    config = FixtureLoader.load_default_config("complete_config")

Directory Structure:
    tests/fixtures/
    ├── __init__.py (this file)
    ├── stock_data/
    │   ├── us_market_ohlcv.json
    │   ├── cn_market_ohlcv.json
    │   └── standardized_ohlcv.json
    ├── metadata/
    │   └── analysis_metadata.json
    ├── report_sections/
    │   └── complete_reports.json
    ├── api_responses/
    │   └── openai_embeddings.json
    └── configurations/
        └── default_config.json
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd


class FixtureLoader:
    """
    Centralized fixture loader for test data.

    Provides static methods for loading various types of test fixtures
    with automatic datetime parsing and DataFrame conversion where appropriate.
    """

    FIXTURES_DIR = Path(__file__).parent

    @classmethod
    def load_json_fixture(cls, relative_path: str) -> Dict[str, Any]:
        """
        Load a JSON fixture file with automatic datetime parsing.

        Converts ISO 8601 datetime strings to Python datetime objects.
        Supports nested dictionaries and lists.

        Args:
            relative_path: Path relative to fixtures directory (e.g., "stock_data/us_market_ohlcv.json")

        Returns:
            Dictionary containing the parsed JSON data with datetime objects

        Raises:
            FileNotFoundError: If fixture file doesn't exist
            json.JSONDecodeError: If file contains invalid JSON

        Example:
            >>> data = FixtureLoader.load_json_fixture("stock_data/us_market_ohlcv.json")
            >>> print(data["ticker"])
            'AAPL'
        """
        fixture_path = cls.FIXTURES_DIR / relative_path

        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture not found: {fixture_path}")

        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Parse datetime strings recursively
        return cls._parse_datetimes(data)

    @classmethod
    def _parse_datetimes(cls, obj: Any) -> Any:
        """
        Recursively parse ISO 8601 datetime strings to datetime objects.

        Handles dictionaries, lists, and nested structures. Attempts to parse
        strings that look like ISO 8601 dates (contain 'T' and ':').

        Args:
            obj: Object to parse (dict, list, str, or other)

        Returns:
            Object with datetime strings converted to datetime objects
        """
        if isinstance(obj, dict):
            return {key: cls._parse_datetimes(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [cls._parse_datetimes(item) for item in obj]
        elif isinstance(obj, str):
            # Try to parse as datetime if it looks like ISO 8601
            if "T" in obj or (obj.count("-") >= 2 and obj.count(":") >= 2):
                try:
                    return datetime.fromisoformat(obj.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    return obj
            return obj
        else:
            return obj

    @classmethod
    def load_dataframe_fixture(
        cls,
        relative_path: str,
        data_key: str = "data",
        date_column: Optional[str] = "Date",
        set_index: bool = True,
    ) -> pd.DataFrame:
        """
        Load a JSON fixture and convert to pandas DataFrame.

        Automatically parses datetime columns and optionally sets date as index.
        Useful for stock OHLCV data and other time-series data.

        Args:
            relative_path: Path to JSON fixture file
            data_key: Key in JSON containing the data array (default: "data")
            date_column: Name of date column to parse (default: "Date")
            set_index: Whether to set date_column as index (default: True)

        Returns:
            pandas DataFrame with parsed dates and optional date index

        Example:
            >>> df = FixtureLoader.load_dataframe_fixture(
            ...     "stock_data/us_market_ohlcv.json",
            ...     data_key="data",
            ...     date_column="Date"
            ... )
            >>> print(df.head())
        """
        fixture_data = cls.load_json_fixture(relative_path)

        # Extract data array
        if data_key not in fixture_data:
            raise KeyError(f"Key '{data_key}' not found in fixture {relative_path}")

        data = fixture_data[data_key]

        # Handle empty data edge case
        if not data:
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(data)

        # Parse date column if specified
        if date_column and date_column in df.columns:
            df[date_column] = pd.to_datetime(df[date_column])

            # Set as index if requested
            if set_index:
                df = df.set_index(date_column)

        return df

    # Stock Data Loaders

    @classmethod
    def load_us_stock_data(
        cls, edge_case: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Load US market stock OHLCV data (AAPL).

        Args:
            edge_case: Optional edge case to load instead of main data.
                       Options: "empty_data", "single_row", "missing_volume",
                       "out_of_order_dates"

        Returns:
            DataFrame with OHLCV data, Date as index

        Example:
            >>> df = FixtureLoader.load_us_stock_data()
            >>> print(df.columns.tolist())
            ['Open', 'High', 'Low', 'Close', 'Volume']
        """
        fixture_data = cls.load_json_fixture("stock_data/us_market_ohlcv.json")

        # Select data source
        if edge_case:
            if "edge_cases" not in fixture_data or edge_case not in fixture_data["edge_cases"]:
                raise ValueError(f"Edge case '{edge_case}' not found in US stock data fixture")
            data = fixture_data["edge_cases"][edge_case]
        else:
            data = fixture_data["data"]

        # Handle empty data
        if not data:
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(data)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")

        return df

    @classmethod
    def load_cn_stock_data(
        cls, edge_case: Optional[str] = None, standardize: bool = False
    ) -> pd.DataFrame:
        """
        Load Chinese market stock OHLCV data (600519.SH - Kweichow Moutai).

        Chinese market data uses localized column names (日期, 开盘, 最高, 最低, 收盘, 成交量).
        Can optionally standardize to English column names.

        Args:
            edge_case: Optional edge case to load instead of main data.
                       Options: "empty_data", "mixed_columns"
            standardize: If True, convert Chinese column names to English

        Returns:
            DataFrame with OHLCV data, date column as index

        Example:
            >>> df = FixtureLoader.load_cn_stock_data()
            >>> print(df.columns.tolist())
            ['开盘', '最高', '最低', '收盘', '成交量']

            >>> df = FixtureLoader.load_cn_stock_data(standardize=True)
            >>> print(df.columns.tolist())
            ['Open', 'High', 'Low', 'Close', 'Volume']
        """
        fixture_data = cls.load_json_fixture("stock_data/cn_market_ohlcv.json")

        # Select data source
        if edge_case:
            if "edge_cases" not in fixture_data or edge_case not in fixture_data["edge_cases"]:
                raise ValueError(f"Edge case '{edge_case}' not found in CN stock data fixture")
            data = fixture_data["edge_cases"][edge_case]
        else:
            data = fixture_data["data"]

        # Handle empty data
        if not data:
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(data)

        # Standardize column names if requested
        if standardize and "column_mapping" in fixture_data:
            column_mapping = fixture_data["column_mapping"]
            df = df.rename(columns=column_mapping)

        # Set date column as index
        date_col = "Date" if standardize else "日期"
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.set_index(date_col)

        return df

    @classmethod
    def load_standardized_stock_data(cls) -> pd.DataFrame:
        """
        Load standardized OHLCV data (TSLA) ready for technical analysis.

        This fixture represents data after standardization - all English column
        names, Date as index, ready for technical indicator calculation.

        Returns:
            DataFrame with standardized OHLCV data

        Example:
            >>> df = FixtureLoader.load_standardized_stock_data()
            >>> print(df.index.name)
            'Date'
        """
        return cls.load_dataframe_fixture(
            "stock_data/standardized_ohlcv.json",
            data_key="data",
            date_column="Date",
            set_index=True,
        )

    # Metadata Loaders

    @classmethod
    def load_analysis_metadata(cls, example_name: str = "complete_analysis") -> Dict[str, Any]:
        """
        Load analysis metadata fixture.

        Provides metadata for stock analysis reports including ticker, date range,
        analysts, vendors, LLM providers, and execution details.

        Args:
            example_name: Name of the example to load.
                          Options: "complete_analysis", "partial_analysis",
                          "multi_ticker_batch", "chinese_market_analysis",
                          "error_scenario"

        Returns:
            Dictionary containing analysis metadata with parsed datetimes

        Example:
            >>> metadata = FixtureLoader.load_analysis_metadata("complete_analysis")
            >>> print(metadata["ticker"])
            'AAPL'
            >>> print(metadata["status"])
            'complete'
        """
        fixture_data = cls.load_json_fixture("metadata/analysis_metadata.json")

        if "examples" not in fixture_data or example_name not in fixture_data["examples"]:
            raise ValueError(f"Example '{example_name}' not found in analysis metadata fixture")

        return fixture_data["examples"][example_name]

    # Report Section Loaders

    @classmethod
    def load_complete_report_sections(cls) -> Dict[str, Dict[str, Any]]:
        """
        Load complete report sections for comprehensive analysis.

        Returns all sections: market_report, sentiment_report, news_report,
        fundamentals_report, investment_plan, trader_investment_plan,
        final_trade_decision.

        Returns:
            Dictionary mapping section names to section data (with content)

        Example:
            >>> sections = FixtureLoader.load_complete_report_sections()
            >>> print(sections["market_report"]["content"][:50])
            '# Market Analysis for AAPL...'
        """
        fixture_data = cls.load_json_fixture("report_sections/complete_reports.json")
        return fixture_data["sections"]

    @classmethod
    def load_partial_report_sections(cls) -> Dict[str, Optional[str]]:
        """
        Load partial report sections (some analysts haven't completed).

        Useful for testing scenarios where only some sections are available.

        Returns:
            Dictionary mapping section names to content (None for incomplete sections)

        Example:
            >>> sections = FixtureLoader.load_partial_report_sections()
            >>> print(sections["market_report"])  # Has content
            >>> print(sections["sentiment_report"])  # None
        """
        fixture_data = cls.load_json_fixture("report_sections/complete_reports.json")
        return fixture_data["partial_sections"]

    @classmethod
    def load_report_section(cls, section_name: str) -> Dict[str, Any]:
        """
        Load a specific report section.

        Args:
            section_name: Name of section to load. Options: "market_report",
                          "sentiment_report", "news_report", "fundamentals_report",
                          "investment_plan", "trader_investment_plan",
                          "final_trade_decision"

        Returns:
            Dictionary containing section metadata and content

        Example:
            >>> section = FixtureLoader.load_report_section("market_report")
            >>> print(section["analyst"])
            'market'
        """
        sections = cls.load_complete_report_sections()

        if section_name not in sections:
            raise ValueError(f"Section '{section_name}' not found in complete reports fixture")

        return sections[section_name]

    # API Response Loaders

    @classmethod
    def load_embedding_response(
        cls, example_name: str = "single_text_embedding"
    ) -> Dict[str, Any]:
        """
        Load OpenAI API embedding response fixture.

        Provides mock API responses for embedding requests, useful for testing
        without making actual API calls.

        Args:
            example_name: Name of the example to load.
                          Options: "single_text_embedding", "batch_text_embeddings",
                          "financial_situation_embedding", "large_embedding_1536"

        Returns:
            Dictionary containing mock OpenAI embedding API response

        Example:
            >>> response = FixtureLoader.load_embedding_response()
            >>> print(response["data"][0]["embedding"][:3])
            [-0.006929283495992422, -0.005336422007530928, 0.00047350498218461871]
        """
        fixture_data = cls.load_json_fixture("api_responses/openai_embeddings.json")

        if "examples" not in fixture_data or example_name not in fixture_data["examples"]:
            raise ValueError(f"Example '{example_name}' not found in embeddings fixture")

        return fixture_data["examples"][example_name]

    @classmethod
    def load_embedding_error(cls, error_type: str = "rate_limit_error") -> Dict[str, Any]:
        """
        Load OpenAI API error response fixture.

        Useful for testing error handling and retry logic.

        Args:
            error_type: Type of error to load.
                        Options: "rate_limit_error", "invalid_api_key", "model_not_found"

        Returns:
            Dictionary containing mock OpenAI error response

        Example:
            >>> error = FixtureLoader.load_embedding_error("rate_limit_error")
            >>> print(error["error"]["type"])
            'rate_limit_error'
        """
        fixture_data = cls.load_json_fixture("api_responses/openai_embeddings.json")

        if "error_responses" not in fixture_data or error_type not in fixture_data["error_responses"]:
            raise ValueError(f"Error type '{error_type}' not found in embeddings fixture")

        return fixture_data["error_responses"][error_type]

    # Configuration Loaders

    @classmethod
    def load_default_config(cls, example_name: str = "complete_config") -> Dict[str, Any]:
        """
        Load configuration fixture.

        Provides default and specialized configurations for testing different
        scenarios and vendor setups.

        Args:
            example_name: Name of the configuration example to load.
                          Options: "complete_config", "minimal_config",
                          "chinese_market_config", "high_frequency_config",
                          "testing_config"

        Returns:
            Dictionary containing configuration settings

        Example:
            >>> config = FixtureLoader.load_default_config("complete_config")
            >>> print(config["data_vendor"])
            'alpaca'
            >>> print(config["llm_provider"])
            'openrouter'
        """
        fixture_data = cls.load_json_fixture("configurations/default_config.json")

        if "examples" not in fixture_data or example_name not in fixture_data["examples"]:
            raise ValueError(f"Example '{example_name}' not found in config fixture")

        return fixture_data["examples"][example_name]

    @classmethod
    def load_vendor_config(cls, vendor_name: str) -> Dict[str, Any]:
        """
        Load vendor-specific configuration.

        Args:
            vendor_name: Name of the vendor.
                         Options: "alpaca", "alpha_vantage", "akshare", "yfinance"

        Returns:
            Dictionary containing vendor-specific configuration

        Example:
            >>> config = FixtureLoader.load_vendor_config("alpaca")
            >>> print(config["paper_trading"])
            True
        """
        fixture_data = cls.load_json_fixture("configurations/default_config.json")

        if "vendor_specific_configs" not in fixture_data or vendor_name not in fixture_data["vendor_specific_configs"]:
            raise ValueError(f"Vendor config '{vendor_name}' not found in config fixture")

        return fixture_data["vendor_specific_configs"][vendor_name]

    @classmethod
    def load_llm_provider_config(cls, provider_name: str) -> Dict[str, Any]:
        """
        Load LLM provider-specific configuration.

        Args:
            provider_name: Name of the LLM provider.
                           Options: "openrouter", "openai", "anthropic", "ollama"

        Returns:
            Dictionary containing LLM provider-specific configuration

        Example:
            >>> config = FixtureLoader.load_llm_provider_config("openrouter")
            >>> print(config["backend_url"])
            'https://openrouter.ai/api/v1'
        """
        fixture_data = cls.load_json_fixture("configurations/default_config.json")

        if "llm_provider_configs" not in fixture_data or provider_name not in fixture_data["llm_provider_configs"]:
            raise ValueError(f"LLM provider config '{provider_name}' not found in config fixture")

        return fixture_data["llm_provider_configs"][provider_name]


# Convenience functions for common use cases

def load_us_stock_data(**kwargs) -> pd.DataFrame:
    """Convenience function for loading US stock data."""
    return FixtureLoader.load_us_stock_data(**kwargs)


def load_cn_stock_data(**kwargs) -> pd.DataFrame:
    """Convenience function for loading Chinese stock data."""
    return FixtureLoader.load_cn_stock_data(**kwargs)


def load_analysis_metadata(example_name: str = "complete_analysis") -> Dict[str, Any]:
    """Convenience function for loading analysis metadata."""
    return FixtureLoader.load_analysis_metadata(example_name)


def load_complete_report_sections() -> Dict[str, Dict[str, Any]]:
    """Convenience function for loading complete report sections."""
    return FixtureLoader.load_complete_report_sections()


def load_embedding_response(example_name: str = "single_text_embedding") -> Dict[str, Any]:
    """Convenience function for loading embedding API responses."""
    return FixtureLoader.load_embedding_response(example_name)


def load_default_config(example_name: str = "complete_config") -> Dict[str, Any]:
    """Convenience function for loading configuration."""
    return FixtureLoader.load_default_config(example_name)


__all__ = [
    "FixtureLoader",
    "load_us_stock_data",
    "load_cn_stock_data",
    "load_analysis_metadata",
    "load_complete_report_sections",
    "load_embedding_response",
    "load_default_config",
]
