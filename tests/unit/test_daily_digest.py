"""Tests for daily_digest.py"""

import pytest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

from tradingagents.daily_digest import append_to_digest

@pytest.fixture
def mock_get_digest_path(tmp_path):
    def _mock_path(date):
        return tmp_path / "reports" / "daily" / date / "daily_digest.md"

    with patch("tradingagents.daily_digest.get_digest_path", side_effect=_mock_path) as mock:
        yield mock

@pytest.fixture
def mock_datetime():
    class MockDatetime:
        @classmethod
        def now(cls):
            return datetime(2023, 10, 26, 14, 30) # 14:30

    with patch("tradingagents.daily_digest.datetime", MockDatetime):
        yield MockDatetime

def test_append_to_digest_new_file(mock_get_digest_path, mock_datetime, tmp_path):
    date = "2023-10-26"
    entry_type = "analyze"
    label = "AAPL"
    content = "Stock is going up."

    result_path = append_to_digest(date, entry_type, label, content)

    expected_path = tmp_path / "reports" / "daily" / date / "daily_digest.md"
    assert result_path == expected_path
    assert result_path.exists()

    expected_content = (
        f"# Daily Trading Report — {date}\n\n"
        f"---\n### 14:30 — {label} ({entry_type})\n\n{content}\n\n"
    )

    assert result_path.read_text() == expected_content

def test_append_to_digest_existing_file(mock_get_digest_path, mock_datetime, tmp_path):
    date = "2023-10-26"

    # First append (creates file)
    append_to_digest(date, "analyze", "AAPL", "First content.")

    # Change time for second append
    with patch("tradingagents.daily_digest.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2023, 10, 26, 15, 45) # 15:45

        # Second append
        result_path = append_to_digest(date, "scan", "Market Scan", "Second content.")

    expected_path = tmp_path / "reports" / "daily" / date / "daily_digest.md"
    assert result_path == expected_path

    expected_content = (
        f"# Daily Trading Report — {date}\n\n"
        f"---\n### 14:30 — AAPL (analyze)\n\nFirst content.\n\n"
        f"---\n### 15:45 — Market Scan (scan)\n\nSecond content.\n\n"
    )

    assert result_path.read_text() == expected_content

def test_append_to_digest_existing_empty_file(mock_get_digest_path, mock_datetime, tmp_path):
    date = "2023-10-26"
    expected_path = tmp_path / "reports" / "daily" / date / "daily_digest.md"
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path.write_text("") # Empty file

    append_to_digest(date, "analyze", "AAPL", "Content")

    # Should treat empty file like a non-existent file and add the header
    expected_content = (
        f"# Daily Trading Report — {date}\n\n"
        f"---\n### 14:30 — AAPL (analyze)\n\nContent\n\n"
    )
    assert expected_path.read_text() == expected_content
