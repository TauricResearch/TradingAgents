"""Tests for tradingagents.memory.reflexion.

Covers:
- Local JSON fallback (no MongoDB)
- record_decision + get_history round-trip
- record_outcome feedback loop
- build_context prompt generation
"""

from __future__ import annotations

import json

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


def test_get_history_excludes_future_decisions(tmp_path):
    """get_history(as_of_date=...) must not return decisions after that date."""
    m = ReflexionMemory(fallback_path=tmp_path / "reflexion.json")
    m.record_decision("AAPL", "2026-01-10", "BUY", "Jan call", run_id="r1")
    m.record_decision("AAPL", "2026-03-15", "HOLD", "Q1 hold", run_id="r2")
    m.record_decision("AAPL", "2026-04-20", "SELL", "Future sell", run_id="r3")

    history = m.get_history("AAPL", limit=10, as_of_date="2026-03-20")
    dates = [r["decision_date"] for r in history]
    assert "2026-04-20" not in dates
    assert "2026-03-15" in dates
    assert "2026-01-10" in dates


def test_get_history_no_as_of_date_returns_all(tmp_path):
    """get_history() without as_of_date returns all decisions (backward-compat)."""
    m = ReflexionMemory(fallback_path=tmp_path / "reflexion.json")
    m.record_decision("AAPL", "2026-01-10", "BUY", "Early", run_id="r1")
    m.record_decision("AAPL", "2026-04-20", "SELL", "Late", run_id="r2")
    history = m.get_history("AAPL", limit=10)
    assert len(history) == 2


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
    result = local_memory.record_outcome("AAPL", "2026-03-20", {"correct": False})
    assert result is False

    history = local_memory.get_history("AAPL")
    assert history[0]["outcome"]["correct"] is True


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------


def test_build_context_with_history(local_memory):
    """build_context should return a formatted multi-line string."""
    local_memory.record_decision("AAPL", "2026-03-20", "BUY", "Strong momentum signal", "high")
    local_memory.record_outcome(
        "AAPL",
        "2026-03-20",
        {
            "price_change_pct": 5.4,
            "correct": True,
        },
    )

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


def test_build_context_excludes_future(tmp_path):
    """build_context(as_of_date=...) must not mention future decisions."""
    m = ReflexionMemory(fallback_path=tmp_path / "reflexion.json")
    m.record_decision("AAPL", "2026-03-15", "HOLD", "Q1 hold rationale", run_id="r1")
    m.record_decision("AAPL", "2026-04-20", "SELL", "Future sell rationale", run_id="r2")

    ctx = m.build_context("AAPL", limit=10, as_of_date="2026-03-20")
    assert "Future sell rationale" not in ctx
    assert "Q1 hold rationale" in ctx


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


def test_corrupt_local_reflexion_logs_warning(tmp_path, caplog):
    """Corrupt local JSON must log a warning, not silently return []."""
    import logging

    bad_path = tmp_path / "corrupt_reflexion.json"
    bad_path.write_text("[{broken", encoding="utf-8")
    m = ReflexionMemory(fallback_path=bad_path)
    with caplog.at_level(logging.WARNING, logger="tradingagents.memory.reflexion"):
        history = m.get_history("AAPL")
    assert history == []
    assert any(
        "corrupt" in r.message.lower() or "malformed" in r.message.lower()
        for r in caplog.records
    )


@pytest.mark.parametrize("payload", ["{}", "[1]"])
def test_structurally_malformed_local_reflexion_logs_warning(tmp_path, caplog, payload):
    """Valid JSON with the wrong shape must warn and return []."""
    import logging

    bad_path = tmp_path / "malformed_reflexion.json"
    bad_path.write_text(payload, encoding="utf-8")
    m = ReflexionMemory(fallback_path=bad_path)
    with caplog.at_level(logging.WARNING, logger="tradingagents.memory.reflexion"):
        history = m.get_history("AAPL")
    assert history == []
    assert any(
        "corrupt" in r.message.lower()
        or "malformed" in r.message.lower()
        or "unreadable" in r.message.lower()
        for r in caplog.records
    )


def test_missing_decision_date_local_reflexion_filters_bad_record_only(tmp_path, caplog):
    """Malformed local records are ignored without discarding valid decisions."""
    import logging

    bad_path = tmp_path / "missing_decision_date_reflexion.json"
    bad_path.write_text(
        json.dumps(
            [
                {
                    "ticker": "AAPL",
                    "decision_date": "2026-03-15",
                    "decision": "HOLD",
                    "rationale": "Valid prior rationale",
                },
                {
                    "ticker": "AAPL",
                    "decision": "BUY",
                    "rationale": "Malformed record",
                }
            ]
        ),
        encoding="utf-8",
    )
    m = ReflexionMemory(fallback_path=bad_path)

    with caplog.at_level(logging.WARNING, logger="tradingagents.memory.reflexion"):
        history = m.get_history("AAPL", limit=5, as_of_date="2026-03-20")

    assert [record["rationale"] for record in history] == ["Valid prior rationale"]
    assert any(
        "corrupt" in r.message.lower()
        or "malformed" in r.message.lower()
        or "unreadable" in r.message.lower()
        for r in caplog.records
    )


def test_local_reflexion_as_of_filter_uses_iso_date_prefix_for_timestamps(tmp_path):
    """Timestamp-shaped local decision dates are compared by YYYY-MM-DD prefix."""
    path = tmp_path / "reflexion.json"
    path.write_text(
        json.dumps(
            [
                {
                    "ticker": "AAPL",
                    "decision_date": "2026-03-15T12:00:00",
                    "decision": "HOLD",
                    "rationale": "Intraday decision",
                },
                {
                    "ticker": "AAPL",
                    "decision_date": "2026-03-16T00:00:00",
                    "decision": "SELL",
                    "rationale": "Future intraday decision",
                },
            ]
        ),
        encoding="utf-8",
    )
    m = ReflexionMemory(fallback_path=path)

    history = m.get_history("AAPL", limit=5, as_of_date="2026-03-15")

    assert [record["rationale"] for record in history] == ["Intraday decision"]


def test_get_history_mongo_query_filters_as_of_date():
    """Mongo get_history(as_of_date=...) must include a decision_date upper bound."""

    class FakeCursor:
        def __init__(self):
            self.sort_args = None
            self.limit_arg = None

        def sort(self, *args):
            self.sort_args = args
            return self

        def limit(self, limit):
            self.limit_arg = limit
            return self

        def __iter__(self):
            return iter([])

    class FakeCollection:
        def __init__(self):
            self.find_args = None
            self.cursor = FakeCursor()

        def find(self, *args):
            self.find_args = args
            return self.cursor

    m = ReflexionMemory(fallback_path="unused.json")
    fake_col = FakeCollection()
    m._col = fake_col

    assert m.get_history("aapl", limit=7, as_of_date="2026-03-20") == []
    query, projection = fake_col.find_args
    assert query == {"ticker": "AAPL", "decision_date": {"$lte": "2026-03-20"}}
    assert projection == {"_id": 0}
    assert fake_col.cursor.limit_arg == 7
