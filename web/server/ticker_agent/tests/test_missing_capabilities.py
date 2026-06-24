"""Tests for missing capabilities tracking."""
from __future__ import annotations

from web.server.ticker_agent.missing_capabilities import (
    log_missing,
    read_missing,
)


def test_log_and_read_missing(tmp_path):
    f = tmp_path / "missing_capabilities.jsonl"
    log_missing("sector_etf_flows", "Track ETF inflows per sector", file_path=str(f))
    log_missing("options_flow", "Monitor unusual options activity", file_path=str(f))
    entries = read_missing(file_path=str(f))
    assert len(entries) == 2
    assert entries[0].name == "options_flow"


def test_read_missing_empty_file(tmp_path):
    f = tmp_path / "missing_capabilities.jsonl"
    f.write_text("")
    assert read_missing(file_path=str(f)) == []


def test_read_missing_file_not_exist(tmp_path):
    assert read_missing(file_path=str(tmp_path / "nonexistent.jsonl")) == []
