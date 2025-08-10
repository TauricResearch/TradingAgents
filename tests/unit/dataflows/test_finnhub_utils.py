"""Unit tests for FinnHub utilities."""

import json
import os

import pytest

from tradingagents.dataflows.finnhub_utils import get_data_in_range


class TestFinnhubUtils:
    """Test suite for FinnHub utility functions."""

    def test_get_data_in_range_basic(self, temp_data_dir):
        """Test basic functionality of get_data_in_range."""
        # Setup test data
        ticker = "AAPL"
        data_type = "news_data"
        test_data = {
            "2024-05-09": [{"headline": "Old news", "summary": "Before range"}],
            "2024-05-10": [{"headline": "Good news", "summary": "In range"}],
            "2024-05-11": [{"headline": "More news", "summary": "Also in range"}],
            "2024-05-12": [{"headline": "Future news", "summary": "After range"}],
        }

        # Create data directory and file
        data_dir = os.path.join(temp_data_dir, "finnhub_data", data_type)
        os.makedirs(data_dir, exist_ok=True)
        data_file = os.path.join(data_dir, f"{ticker}_data_formatted.json")

        with open(data_file, "w") as f:
            json.dump(test_data, f)

        # Execute
        result = get_data_in_range(
            ticker=ticker,
            start_date="2024-05-10",
            end_date="2024-05-11",
            data_type=data_type,
            data_dir=temp_data_dir,
        )

        # Verify
        assert len(result) == 2
        assert "2024-05-10" in result
        assert "2024-05-11" in result
        assert "2024-05-09" not in result
        assert "2024-05-12" not in result
        assert result["2024-05-10"][0]["headline"] == "Good news"
        assert result["2024-05-11"][0]["headline"] == "More news"

    def test_get_data_in_range_with_period(self, temp_data_dir):
        """Test get_data_in_range with period parameter."""
        ticker = "TSLA"
        data_type = "fin_as_reported"
        period = "quarterly"
        test_data = {
            "2024-03-31": [{"revenue": 21301000000, "period": "Q1"}],
            "2024-06-30": [{"revenue": 24927000000, "period": "Q2"}],
        }

        # Create data directory and file
        data_dir = os.path.join(temp_data_dir, "finnhub_data", data_type)
        os.makedirs(data_dir, exist_ok=True)
        data_file = os.path.join(data_dir, f"{ticker}_{period}_data_formatted.json")

        with open(data_file, "w") as f:
            json.dump(test_data, f)

        # Execute
        result = get_data_in_range(
            ticker=ticker,
            start_date="2024-03-01",
            end_date="2024-06-30",
            data_type=data_type,
            data_dir=temp_data_dir,
            period=period,
        )

        # Verify
        assert len(result) == 2
        assert "2024-03-31" in result
        assert "2024-06-30" in result
        assert result["2024-03-31"][0]["revenue"] == 21301000000

    def test_get_data_in_range_filters_empty_values(self, temp_data_dir):
        """Test that empty values are filtered out."""
        ticker = "NVDA"
        data_type = "insider_trans"
        test_data = {
            "2024-05-10": [{"transaction": "buy", "shares": 1000}],
            "2024-05-11": [],  # Empty array should be filtered
            "2024-05-12": [{"transaction": "sell", "shares": 500}],
        }

        # Create data directory and file
        data_dir = os.path.join(temp_data_dir, "finnhub_data", data_type)
        os.makedirs(data_dir, exist_ok=True)
        data_file = os.path.join(data_dir, f"{ticker}_data_formatted.json")

        with open(data_file, "w") as f:
            json.dump(test_data, f)

        # Execute
        result = get_data_in_range(
            ticker=ticker,
            start_date="2024-05-10",
            end_date="2024-05-12",
            data_type=data_type,
            data_dir=temp_data_dir,
        )

        # Verify - empty array should be filtered out
        assert len(result) == 2
        assert "2024-05-10" in result
        assert "2024-05-11" not in result  # Should be filtered out
        assert "2024-05-12" in result

    def test_get_data_in_range_date_boundary(self, temp_data_dir):
        """Test date boundary conditions."""
        ticker = "MSFT"
        data_type = "SEC_filings"
        test_data = {
            "2024-05-09": [{"filing": "10-Q"}],
            "2024-05-10": [{"filing": "8-K"}],  # Start date (inclusive)
            "2024-05-11": [{"filing": "10-K"}],
            "2024-05-12": [{"filing": "DEF 14A"}],  # End date (inclusive)
            "2024-05-13": [{"filing": "Schedule 13D"}],
        }

        # Create data directory and file
        data_dir = os.path.join(temp_data_dir, "finnhub_data", data_type)
        os.makedirs(data_dir, exist_ok=True)
        data_file = os.path.join(data_dir, f"{ticker}_data_formatted.json")

        with open(data_file, "w") as f:
            json.dump(test_data, f)

        # Execute
        result = get_data_in_range(
            ticker=ticker,
            start_date="2024-05-10",
            end_date="2024-05-12",
            data_type=data_type,
            data_dir=temp_data_dir,
        )

        # Verify - both boundary dates should be included
        assert len(result) == 3
        assert "2024-05-10" in result
        assert "2024-05-11" in result
        assert "2024-05-12" in result
        assert "2024-05-09" not in result
        assert "2024-05-13" not in result

    def test_get_data_in_range_no_matching_data(self, temp_data_dir):
        """Test behavior when no data matches the date range."""
        ticker = "AMZN"
        data_type = "insider_senti"
        test_data = {
            "2024-04-01": [{"sentiment": "positive"}],
            "2024-04-02": [{"sentiment": "neutral"}],
        }

        # Create data directory and file
        data_dir = os.path.join(temp_data_dir, "finnhub_data", data_type)
        os.makedirs(data_dir, exist_ok=True)
        data_file = os.path.join(data_dir, f"{ticker}_data_formatted.json")

        with open(data_file, "w") as f:
            json.dump(test_data, f)

        # Execute - request data from a different time range
        result = get_data_in_range(
            ticker=ticker,
            start_date="2024-05-10",
            end_date="2024-05-12",
            data_type=data_type,
            data_dir=temp_data_dir,
        )

        # Verify - should return empty dict
        assert len(result) == 0
        assert result == {}

    def test_get_data_in_range_file_handling(self, temp_data_dir):
        """Test proper file path construction and handling."""
        ticker = "GOOGL"
        data_type = "news_data"

        # Test without period
        expected_path_no_period = os.path.join(
            temp_data_dir, "finnhub_data", data_type, f"{ticker}_data_formatted.json",
        )

        # Test with period
        period = "annual"
        expected_path_with_period = os.path.join(
            temp_data_dir,
            "finnhub_data",
            data_type,
            f"{ticker}_{period}_data_formatted.json",
        )

        # Create test data for both scenarios
        test_data = {"2024-05-10": [{"test": "data"}]}

        # Create directories
        data_dir = os.path.join(temp_data_dir, "finnhub_data", data_type)
        os.makedirs(data_dir, exist_ok=True)

        # Create files
        with open(expected_path_no_period, "w") as f:
            json.dump(test_data, f)
        with open(expected_path_with_period, "w") as f:
            json.dump(test_data, f)

        # Test without period
        result1 = get_data_in_range(
            ticker=ticker,
            start_date="2024-05-10",
            end_date="2024-05-10",
            data_type=data_type,
            data_dir=temp_data_dir,
        )
        assert len(result1) == 1

        # Test with period
        result2 = get_data_in_range(
            ticker=ticker,
            start_date="2024-05-10",
            end_date="2024-05-10",
            data_type=data_type,
            data_dir=temp_data_dir,
            period=period,
        )
        assert len(result2) == 1

    @pytest.mark.parametrize(
        ("data_type", "period"),
        [
            ("news_data", None),
            ("insider_trans", None),
            ("SEC_filings", None),
            ("insider_senti", None),
            ("fin_as_reported", "annual"),
            ("fin_as_reported", "quarterly"),
        ],
    )
    def test_get_data_in_range_various_data_types(
        self, temp_data_dir, data_type, period,
    ):
        """Test get_data_in_range with various data types."""
        ticker = "TEST"
        test_data = {
            "2024-05-10": [{"test_field": "test_value"}],
        }

        # Create data directory and file
        data_dir = os.path.join(temp_data_dir, "finnhub_data", data_type)
        os.makedirs(data_dir, exist_ok=True)

        filename = f"{ticker}_data_formatted.json"
        if period:
            filename = f"{ticker}_{period}_data_formatted.json"

        data_file = os.path.join(data_dir, filename)

        with open(data_file, "w") as f:
            json.dump(test_data, f)

        # Execute
        result = get_data_in_range(
            ticker=ticker,
            start_date="2024-05-10",
            end_date="2024-05-10",
            data_type=data_type,
            data_dir=temp_data_dir,
            period=period,
        )

        # Verify
        assert len(result) == 1
        assert "2024-05-10" in result
        assert result["2024-05-10"][0]["test_field"] == "test_value"


class TestFinnhubUtilsErrorHandling:
    """Test error handling in FinnHub utilities."""

    def test_get_data_in_range_missing_file(self, temp_data_dir):
        """Test behavior when data file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            get_data_in_range(
                ticker="NONEXISTENT",
                start_date="2024-05-10",
                end_date="2024-05-11",
                data_type="news_data",
                data_dir=temp_data_dir,
            )

    def test_get_data_in_range_invalid_json(self, temp_data_dir):
        """Test behavior when JSON file is corrupted."""
        ticker = "CORRUPT"
        data_type = "news_data"

        # Create data directory and corrupted file
        data_dir = os.path.join(temp_data_dir, "finnhub_data", data_type)
        os.makedirs(data_dir, exist_ok=True)
        data_file = os.path.join(data_dir, f"{ticker}_data_formatted.json")

        with open(data_file, "w") as f:
            f.write("invalid json content")

        # Should raise JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            get_data_in_range(
                ticker=ticker,
                start_date="2024-05-10",
                end_date="2024-05-11",
                data_type=data_type,
                data_dir=temp_data_dir,
            )
