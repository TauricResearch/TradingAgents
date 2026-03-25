"""Tests for tradingagents.memory.reflexion.

Covers:
- Local JSON fallback (no MongoDB)
- record_decision + get_history round-trip
- record_outcome feedback loop
- build_context prompt generation
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradingagents.memory.reflexion import ReflexionMemory


@pytest.fixture
def local_memory(tmp_path):
    """Return a ReflexionMemory using local JSON fallback."""
    return ReflexionMemory(
        mongo_uri=None,
        fallback_path=tmp_path / "reflexion.json",
    )


# ---------------------------------------------------------------------------
# record_decision + get_history
# ---------------------------------------------------------------------------


def test_record_and_get_history(local_memory):
    """record_decision then get_history should return the decision."""
    local_memory.record_decision(
        ticker="AAPL",
        date="2026-03-20",
        decision="BUY",
        rationale="Strong fundamentals and momentum",
        confidence="high",
        source="pipeline",
        run_id="test_run",
    )

    history = local_memory.get_history("AAPL")
    assert len(history) == 1
    rec = history[0]
    assert rec["ticker"] == "AAPL"
    assert rec["decision"] == "BUY"
    assert rec["confidence"] == "high"
    assert rec["rationale"] == "Strong fundamentals and momentum"
    assert rec["outcome"] is None


def test_multiple_decisions_sorted_newest_first(local_memory):
    """get_history should return decisions sorted by date, newest first."""
    for i, date in enumerate(["2026-03-18", "2026-03-19", "2026-03-20"]):
        local_memory.record_decision(
            ticker="MSFT",
            date=date,
            decision=["HOLD", "BUY", "SELL"][i],
            rationale=f"Reason {i}",
        )

    history = local_memory.get_history("MSFT")
    assert len(history) == 3
    assert history[0]["decision_date"] == "2026-03-20"
    assert history[1]["decision_date"] == "2026-03-19"
    assert history[2]["decision_date"] == "2026-03-18"


def test_get_history_limit(local_memory):
    """get_history with limit should return at most that many records."""
    for i in range(10):
        local_memory.record_decision(
            ticker="GOOGL",
            date=f"2026-03-{10 + i:02d}",
            decision="HOLD",
            rationale=f"Decision {i}",
        )

    history = local_memory.get_history("GOOGL", limit=3)
    assert len(history) == 3


def test_get_history_filters_by_ticker(local_memory):
    """get_history should only return decisions for the requested ticker."""
    local_memory.record_decision("AAPL", "2026-03-20", "BUY", "reason")
    local_memory.record_decision("MSFT", "2026-03-20", "SELL", "reason")

    aapl_history = local_memory.get_history("AAPL")
    assert len(aapl_history) == 1
    assert aapl_history[0]["ticker"] == "AAPL"


def test_ticker_stored_as_uppercase(local_memory):
    """Tickers should be normalized to uppercase."""
    local_memory.record_decision("aapl", "2026-03-20", "buy", "reason")

    history = local_memory.get_history("AAPL")
    assert len(history) == 1
    assert history[0]["ticker"] == "AAPL"
    assert history[0]["decision"] == "BUY"


# ---------------------------------------------------------------------------
# record_outcome
# ---------------------------------------------------------------------------


def test_record_outcome_updates_decision(local_memory):
    """record_outcome should attach outcome data to the matching decision."""
    local_memory.record_decision("AAPL", "2026-03-20", "BUY", "reason")

    outcome = {
        "evaluation_date": "2026-04-20",
        "price_at_decision": 185.0,
        "price_at_evaluation": 195.0,
        "price_change_pct": 5.4,
        "correct": True,
    }
    result = local_memory.record_outcome("AAPL", "2026-03-20", outcome)

    assert result is True
    history = local_memory.get_history("AAPL")
    assert history[0]["outcome"] == outcome


def test_record_outcome_returns_false_when_no_match(local_memory):
    """record_outcome should return False when no matching decision exists."""
    result = local_memory.record_outcome("AAPL", "2026-03-20", {"correct": True})
    assert result is False


def test_record_outcome_only_fills_null_outcome(local_memory):
    """record_outcome should only update decisions that have outcome=None."""
    local_memory.record_decision("AAPL", "2026-03-20", "BUY", "reason")
    local_memory.record_outcome("AAPL", "2026-03-20", {"correct": True})

    # Second outcome should not overwrite
    result = local_memory.record_outcome(
        "AAPL", "2026-03-20", {"correct": False}
    )
    assert result is False

    history = local_memory.get_history("AAPL")
    assert history[0]["outcome"]["correct"] is True


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------


def test_build_context_with_history(local_memory):
    """build_context should return a formatted multi-line string."""
    local_memory.record_decision(
        "AAPL", "2026-03-20", "BUY", "Strong momentum signal", "high"
    )
    local_memory.record_outcome("AAPL", "2026-03-20", {
        "price_change_pct": 5.4,
        "correct": True,
    })

    context = local_memory.build_context("AAPL")

    assert "2026-03-20" in context
    assert "BUY" in context
    assert "high" in context
    assert "5.4% change" in context
    assert "correct=True" in context


def test_build_context_no_history(local_memory):
    """build_context with no history should return an informative message."""
    context = local_memory.build_context("ZZZZZ")
    assert "No prior decisions" in context


def test_build_context_pending_outcome(local_memory):
    """build_context with pending outcome should show 'pending'."""
    local_memory.record_decision("AAPL", "2026-03-20", "BUY", "reason")

    context = local_memory.build_context("AAPL")
    assert "pending" in context


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_local_file_persists_across_instances(tmp_path):
    """Decisions written by one instance should be readable by another."""
    fb_path = tmp_path / "reflexion.json"

    mem1 = ReflexionMemory(fallback_path=fb_path)
    mem1.record_decision("AAPL", "2026-03-20", "BUY", "reason")

    mem2 = ReflexionMemory(fallback_path=fb_path)
    history = mem2.get_history("AAPL")
    assert len(history) == 1


def test_local_file_created_on_first_write(tmp_path):
    """The local JSON file should be created on the first record_decision."""
    fb_path = tmp_path / "subdir" / "reflexion.json"
    assert not fb_path.exists()

    mem = ReflexionMemory(fallback_path=fb_path)
    mem.record_decision("AAPL", "2026-03-20", "BUY", "reason")

    assert fb_path.exists()
    data = json.loads(fb_path.read_text())
    assert len(data) == 1
