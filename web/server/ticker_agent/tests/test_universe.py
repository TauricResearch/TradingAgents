"""Tests for ticker universe discovery."""
from __future__ import annotations

from web.server.ticker_agent.universe import (
    load_custom_universe,
    merge_and_dedup,
)


def test_merge_and_dedup():
    sources = {
        "sp500": ["AAPL", "MSFT", "NVDA"],
        "watchlist": ["NVDA", "TSLA"],
        "custom": ["AAPL", "AMZN"],
    }
    merged = merge_and_dedup(sources)
    assert sorted(merged) == sorted(["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"])


def test_load_custom_universe_missing_file_returns_empty(tmp_path):
    result = load_custom_universe(tmp_path / "nonexistent.json")
    assert result == []


def test_load_custom_universe_reads_json(tmp_path):
    f = tmp_path / "universe.json"
    f.write_text('["AAPL", "MSFT", "NVDA"]')
    result = load_custom_universe(str(f))
    assert sorted(result) == sorted(["AAPL", "MSFT", "NVDA"])
