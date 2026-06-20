"""Tests for the multi-ticker parallel run feature.

Covers the pure / fast bits: watchlist parsing and the worker's stage-derivation
helper. The LLM-bound worker entry point (``_run_one``) is not exercised here —
it would require a graph and live API calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.multi_runner import _derive_stage
from cli.utils import parse_watchlist


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_watchlist_basic_entries(tmp_path):
    f = _write(
        tmp_path / "w.txt",
        "NVDA 800\nAAPL\n0700.HK 1500\n",
    )
    entries = parse_watchlist(f)
    assert entries == [("NVDA", 800.0), ("AAPL", None), ("0700.HK", 1500.0)]


def test_parse_watchlist_tolerates_pound_and_comma(tmp_path):
    f = _write(tmp_path / "w.txt", "NVDA £1,250\n")
    entries = parse_watchlist(f)
    assert entries == [("NVDA", 1250.0)]


def test_parse_watchlist_comments_and_blank_lines(tmp_path):
    f = _write(
        tmp_path / "w.txt",
        "# top\nNVDA 800 # primary holding\n\n# spacer\nAAPL\n",
    )
    entries = parse_watchlist(f)
    assert entries == [("NVDA", 800.0), ("AAPL", None)]


def test_parse_watchlist_dedupes_keeping_first(tmp_path):
    f = _write(tmp_path / "w.txt", "NVDA 800\nNVDA 999\n")
    entries = parse_watchlist(f)
    assert entries == [("NVDA", 800.0)]


def test_parse_watchlist_rejects_invalid_amount(tmp_path):
    f = _write(tmp_path / "w.txt", "NVDA abc\n")
    with pytest.raises(ValueError, match="could not parse position size"):
        parse_watchlist(f)


def test_parse_watchlist_rejects_negative_amount(tmp_path):
    f = _write(tmp_path / "w.txt", "NVDA -100\n")
    with pytest.raises(ValueError, match="must be positive"):
        parse_watchlist(f)


def test_parse_watchlist_rejects_invalid_ticker(tmp_path):
    f = _write(tmp_path / "w.txt", "BAD$TICKER\n")
    with pytest.raises(ValueError, match="invalid ticker symbol"):
        parse_watchlist(f)


def test_parse_watchlist_rejects_empty_file(tmp_path):
    f = _write(tmp_path / "w.txt", "# only comments\n\n")
    with pytest.raises(ValueError, match="no tickers found"):
        parse_watchlist(f)


def test_parse_watchlist_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_watchlist(tmp_path / "does_not_exist.txt")


def test_derive_stage_progression():
    assert _derive_stage({}) == "queued"
    assert _derive_stage({"market_report": "x"}) == "analysts"
    assert _derive_stage({"investment_debate_state": {"bull_history": "x"}}) == "research_debate"
    assert _derive_stage({"trader_investment_plan": "x"}) == "trader"
    assert _derive_stage({"risk_debate_state": {"aggressive_history": "x"}}) == "risk_debate"
    assert _derive_stage({"final_trade_decision": "x"}) == "portfolio"


def test_derive_stage_picks_latest_when_multiple_present():
    # Cumulative state with multiple fields filled should report the latest stage,
    # since stream_mode="values" emits the full state at each node boundary.
    chunk = {
        "market_report": "x",
        "investment_debate_state": {"judge_decision": "x"},
        "trader_investment_plan": "x",
        "final_trade_decision": "x",
    }
    assert _derive_stage(chunk) == "portfolio"
