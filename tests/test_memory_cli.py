"""Tests for the trade-decision decision-log CLI (tradingagents.mcp.memory_cli).

Exercises the store -> pending -> resolve -> get-context round trip against a
temporary log path, and asserts the on-disk format stays compatible with
``TradingMemoryLog`` (the native pipeline reads the same file).
"""

import json

import pytest

from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.mcp import memory_cli


@pytest.fixture()
def temp_log(tmp_path, monkeypatch):
    """Point memory_cli at a temp log by patching the config it loads."""
    log_path = tmp_path / "trading_memory.md"

    def fake_memory_log():
        return TradingMemoryLog({"memory_log_path": str(log_path)})

    monkeypatch.setattr(memory_cli, "_memory_log", fake_memory_log)
    return log_path


def _run(argv, capsys):
    rc = memory_cli.main(argv)
    out = capsys.readouterr().out
    return rc, out


@pytest.mark.unit
def test_store_then_pending_lists_entry(temp_log, tmp_path, capsys):
    decision = tmp_path / "decision.md"
    decision.write_text("**Rating**: Buy\n\n**Executive Summary**: ok.", encoding="utf-8")

    rc, _ = _run(["store", "NVDA", "2026-01-15", "--decision-file", str(decision)], capsys)
    assert rc == 0

    rc, out = _run(["pending", "NVDA"], capsys)
    assert rc == 0
    pending = json.loads(out)
    assert pending == [{"date": "2026-01-15", "rating": "Buy"}]


@pytest.mark.unit
def test_pending_is_ticker_scoped(temp_log, tmp_path, capsys):
    for tkr in ("NVDA", "AAPL"):
        d = tmp_path / f"{tkr}.md"
        d.write_text("**Rating**: Hold", encoding="utf-8")
        _run(["store", tkr, "2026-01-15", "--decision-file", str(d)], capsys)

    rc, out = _run(["pending", "AAPL"], capsys)
    assert [e["date"] for e in json.loads(out)] == ["2026-01-15"]
    assert all(e["rating"] == "Hold" for e in json.loads(out))


@pytest.mark.unit
def test_resolve_adds_returns_and_reflection_to_context(temp_log, tmp_path, capsys):
    decision = tmp_path / "decision.md"
    decision.write_text("**Rating**: Buy\n\n**Executive Summary**: ok.", encoding="utf-8")
    _run(["store", "NVDA", "2026-01-15", "--decision-file", str(decision)], capsys)

    reflection = tmp_path / "refl.md"
    reflection.write_text("Modest alpha; thesis held.", encoding="utf-8")
    rc, _ = _run(
        [
            "resolve", "NVDA", "2026-01-15",
            "--raw", "0.034", "--alpha", "-0.012", "--holding", "5",
            "--reflection-file", str(reflection),
        ],
        capsys,
    )
    assert rc == 0

    # Resolved entries (not pending) now surface in get-context.
    rc, out = _run(["get-context", "NVDA"], capsys)
    assert "Past analyses of NVDA" in out
    assert "+3.4%" in out and "-1.2%" in out and "5d" in out
    assert "Modest alpha; thesis held." in out

    # And the resolved entry is no longer pending.
    rc, out = _run(["pending", "NVDA"], capsys)
    assert json.loads(out) == []


@pytest.mark.unit
def test_on_disk_format_is_readable_by_native_memory_log(temp_log, tmp_path, capsys):
    decision = tmp_path / "decision.md"
    decision.write_text("**Rating**: Overweight\n\n**Thesis**: x.", encoding="utf-8")
    _run(["store", "TSLA", "2026-02-01", "--decision-file", str(decision)], capsys)

    # The native log parser must understand what the CLI wrote.
    native = TradingMemoryLog({"memory_log_path": str(temp_log)})
    entries = native.load_entries()
    assert len(entries) == 1
    assert entries[0]["ticker"] == "TSLA"
    assert entries[0]["rating"] == "Overweight"
    assert entries[0]["pending"] is True
