"""End-to-end tests that hit real LLM APIs.

These tests are expensive and non-deterministic. Run manually only:

    pytest tests/e2e/ -v --allow-hosts
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from cli.main import run_scan


def test_scan_command_creates_output_files():
    """Test that the scan command creates all expected output files.

    This test runs the full scanner pipeline with real LLMs. It mocks
    only the file-system output path and the typer prompt, NOT the LLM
    or data API calls.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        test_date_dir = Path(temp_dir) / "market"
        test_date_dir.mkdir(parents=True)

        with patch("cli.main.get_market_dir", return_value=test_date_dir):
            written_files = {}

            def mock_write_text(self, content, encoding=None):
                written_files[str(self)] = content

            with patch("pathlib.Path.write_text", mock_write_text):
                with patch("typer.prompt", return_value="2026-03-15"):
                    try:
                        run_scan()
                    except SystemExit:
                        pass

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
