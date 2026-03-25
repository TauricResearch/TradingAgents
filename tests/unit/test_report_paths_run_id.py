"""Tests for run_id support in report_paths.py.

Covers:
- generate_run_id uniqueness and format
- latest.json pointer mechanism (write + read)
- path helpers with and without run_id
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tradingagents import report_paths
from tradingagents.report_paths import (
    generate_run_id,
    get_daily_dir,
    get_digest_path,
    get_eval_dir,
    get_market_dir,
    get_ticker_dir,
    read_latest_pointer,
    write_latest_pointer,
)


# ---------------------------------------------------------------------------
# generate_run_id
# ---------------------------------------------------------------------------


def test_generate_run_id_format():
    """Run IDs should be 8-char lowercase hex strings."""
    rid = generate_run_id()
    assert len(rid) == 8
    assert all(c in "0123456789abcdef" for c in rid)


def test_generate_run_id_unique():
    """Consecutive run IDs should not collide."""
    ids = {generate_run_id() for _ in range(100)}
    assert len(ids) == 100


# ---------------------------------------------------------------------------
# latest.json pointer
# ---------------------------------------------------------------------------


def test_write_and_read_latest_pointer(tmp_path):
    """write_latest_pointer then read_latest_pointer must round-trip."""
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        write_latest_pointer("2026-03-20", "abc12345")
        result = read_latest_pointer("2026-03-20")

    assert result == "abc12345"
    pointer = tmp_path / "daily" / "2026-03-20" / "latest.json"
    assert pointer.exists()
    data = json.loads(pointer.read_text())
    assert data["run_id"] == "abc12345"
    assert "updated_at" in data


def test_read_latest_pointer_returns_none_when_missing(tmp_path):
    """read_latest_pointer returns None when no pointer file exists."""
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        assert read_latest_pointer("2026-01-01") is None


def test_write_latest_pointer_overwrites(tmp_path):
    """Writing a new pointer should overwrite the old one."""
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        write_latest_pointer("2026-03-20", "first")
        write_latest_pointer("2026-03-20", "second")
        result = read_latest_pointer("2026-03-20")

    assert result == "second"


# ---------------------------------------------------------------------------
# Path helpers — no run_id (backward compatible)
# ---------------------------------------------------------------------------


def test_get_daily_dir_no_run_id(tmp_path):
    """Without run_id, get_daily_dir returns the flat date path."""
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_daily_dir("2026-03-20")
    assert result == tmp_path / "daily" / "2026-03-20"


def test_get_market_dir_no_run_id(tmp_path):
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_market_dir("2026-03-20")
    assert result == tmp_path / "daily" / "2026-03-20" / "market"


def test_get_ticker_dir_no_run_id(tmp_path):
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_ticker_dir("2026-03-20", "AAPL")
    assert result == tmp_path / "daily" / "2026-03-20" / "AAPL"


def test_get_eval_dir_no_run_id(tmp_path):
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_eval_dir("2026-03-20", "msft")
    assert result == tmp_path / "daily" / "2026-03-20" / "MSFT" / "eval"


def test_get_digest_path_always_at_date_level(tmp_path):
    """Digest path is always at the date level, not scoped by run_id."""
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_digest_path("2026-03-20")
    assert result == tmp_path / "daily" / "2026-03-20" / "daily_digest.md"


# ---------------------------------------------------------------------------
# Path helpers — with run_id
# ---------------------------------------------------------------------------


def test_get_daily_dir_with_run_id(tmp_path):
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_daily_dir("2026-03-20", run_id="abc12345")
    assert result == tmp_path / "daily" / "2026-03-20" / "runs" / "abc12345"


def test_get_market_dir_with_run_id(tmp_path):
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_market_dir("2026-03-20", run_id="abc12345")
    assert result == tmp_path / "daily" / "2026-03-20" / "runs" / "abc12345" / "market"


def test_get_ticker_dir_with_run_id(tmp_path):
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_ticker_dir("2026-03-20", "AAPL", run_id="abc12345")
    assert result == tmp_path / "daily" / "2026-03-20" / "runs" / "abc12345" / "AAPL"


def test_get_eval_dir_with_run_id(tmp_path):
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_eval_dir("2026-03-20", "AAPL", run_id="abc12345")
    assert result == tmp_path / "daily" / "2026-03-20" / "runs" / "abc12345" / "AAPL" / "eval"
