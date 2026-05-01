"""Tests for MacroMemory — regime-level learning memory.

Covers:
- record_macro_state + get_recent round-trip (local JSON fallback)
- build_macro_context formatting
- record_outcome feedback loop
- Ordering guarantees (newest-first)
- Persistence across instances
"""

from __future__ import annotations

import json

import pytest

from tradingagents.memory.macro_memory import MacroMemory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mem(tmp_path):
    """Return a MacroMemory using local JSON fallback in a temp directory."""
    return MacroMemory(fallback_path=tmp_path / "macro.json")


# ---------------------------------------------------------------------------
# record_macro_state + get_recent
# ---------------------------------------------------------------------------


class TestMacroMemoryLocalFallback:
    """Tests using local JSON fallback (no MongoDB needed)."""

    def test_record_and_retrieve(self, tmp_path):
        """record_macro_state() stores and get_recent() retrieves."""
        m = MacroMemory(fallback_path=tmp_path / "macro.json")
        m.record_macro_state(
            date="2026-03-26",
            vix_level=25.3,
            macro_call="risk-off",
            sector_thesis="Energy under pressure",
            key_themes=["rate hikes", "oil volatility"],
        )
        records = m.get_recent(limit=5)
        assert len(records) == 1
        assert records[0]["macro_call"] == "risk-off"
        assert records[0]["vix_level"] == 25.3

    def test_build_macro_context_no_history(self, tmp_path):
        """build_macro_context() returns a message when no history."""
        m = MacroMemory(fallback_path=tmp_path / "macro.json")
        ctx = m.build_macro_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_build_macro_context_with_history(self, tmp_path):
        """build_macro_context() includes date, macro_call, vix."""
        m = MacroMemory(fallback_path=tmp_path / "macro.json")
        m.record_macro_state("2026-03-20", 28.0, "risk-off", "hawkish Fed", ["rates"])
        ctx = m.build_macro_context(limit=1)
        assert "2026-03-20" in ctx
        assert "risk-off" in ctx or "28" in ctx  # either VIX or call shows up

    def test_record_outcome(self, tmp_path):
        """record_outcome() attaches an outcome dict to the matching record."""
        m = MacroMemory(fallback_path=tmp_path / "macro.json")
        m.record_macro_state("2026-03-20", 25.0, "neutral", "mixed signals", [])
        ok = m.record_outcome("2026-03-20", {"correct": True, "note": "regime held"})
        assert ok is True
        records = m.get_recent()
        assert records[0]["outcome"] is not None

    def test_get_recent_newest_first(self, tmp_path):
        """get_recent() returns records sorted newest-first."""
        m = MacroMemory(fallback_path=tmp_path / "macro.json")
        m.record_macro_state("2026-03-01", 20.0, "risk-on", "", [])
        m.record_macro_state("2026-03-26", 25.0, "risk-off", "", [])
        records = m.get_recent(limit=2)
        assert records[0]["regime_date"] == "2026-03-26"
        assert records[1]["regime_date"] == "2026-03-01"

    def test_get_recent_excludes_future_records(self, tmp_path):
        """get_recent(as_of_date=...) must not return records after that date."""
        m = MacroMemory(fallback_path=tmp_path / "macro.json")
        m.record_macro_state(
            date="2026-01-10",
            vix_level=20.0,
            macro_call="neutral",
            sector_thesis="Early year",
            key_themes=["rates"],
        )
        m.record_macro_state(
            date="2026-03-15",
            vix_level=25.0,
            macro_call="risk-off",
            sector_thesis="Q1 sell-off",
            key_themes=["inflation"],
        )
        m.record_macro_state(
            date="2026-04-20",
            vix_level=18.0,
            macro_call="risk-on",
            sector_thesis="Recovery",
            key_themes=["earnings"],
        )
        records = m.get_recent(limit=10, as_of_date="2026-03-20")
        dates = [r["regime_date"] for r in records]
        assert "2026-04-20" not in dates
        assert "2026-03-15" in dates
        assert "2026-01-10" in dates

    def test_build_macro_context_excludes_future(self, tmp_path):
        """build_macro_context(as_of_date=...) must not include future records in output."""
        m = MacroMemory(fallback_path=tmp_path / "macro.json")
        m.record_macro_state(
            date="2026-03-15",
            vix_level=25.0,
            macro_call="risk-off",
            sector_thesis="Q1 sell-off",
            key_themes=["inflation"],
        )
        m.record_macro_state(
            date="2026-04-20",
            vix_level=18.0,
            macro_call="risk-on",
            sector_thesis="Future recovery",
            key_themes=["earnings"],
        )
        ctx = m.build_macro_context(limit=10, as_of_date="2026-03-20")
        assert "Future recovery" not in ctx
        assert "Q1 sell-off" in ctx

    def test_get_recent_no_as_of_date_returns_all(self, tmp_path):
        """get_recent() without as_of_date returns all records (backward-compat)."""
        m = MacroMemory(fallback_path=tmp_path / "macro.json")
        m.record_macro_state(
            date="2026-01-10",
            vix_level=20.0,
            macro_call="neutral",
            sector_thesis="Early",
            key_themes=[],
        )
        m.record_macro_state(
            date="2026-04-20",
            vix_level=18.0,
            macro_call="risk-on",
            sector_thesis="Late",
            key_themes=[],
        )
        records = m.get_recent(limit=10)
        assert len(records) == 2

    def test_corrupt_local_file_logs_warning(self, tmp_path, caplog):
        """Corrupt local JSON must log a warning, not silently return []."""
        import logging

        bad_path = tmp_path / "corrupt.json"
        bad_path.write_text("{not valid json}", encoding="utf-8")
        m = MacroMemory(fallback_path=bad_path)
        with caplog.at_level(logging.WARNING, logger="tradingagents.memory.macro_memory"):
            records = m.get_recent(limit=5)
        assert records == []
        assert any(
            "corrupt" in r.message.lower() or "malformed" in r.message.lower()
            for r in caplog.records
        )

    @pytest.mark.parametrize("payload", ["{}", "[1]"])
    def test_structurally_malformed_local_file_logs_warning(self, tmp_path, caplog, payload):
        """Valid JSON with the wrong shape must warn and return []."""
        import logging

        bad_path = tmp_path / "malformed.json"
        bad_path.write_text(payload, encoding="utf-8")
        m = MacroMemory(fallback_path=bad_path)
        with caplog.at_level(logging.WARNING, logger="tradingagents.memory.macro_memory"):
            records = m.get_recent(limit=5)
        assert records == []
        assert any(
            "corrupt" in r.message.lower()
            or "malformed" in r.message.lower()
            or "unreadable" in r.message.lower()
            for r in caplog.records
        )

    def test_missing_regime_date_local_record_is_filtered_without_losing_valid_records(
        self, tmp_path, caplog
    ):
        """Malformed local records are ignored without discarding valid history."""
        import logging

        bad_path = tmp_path / "missing_regime_date.json"
        bad_path.write_text(
            json.dumps(
                [
                    {
                        "regime_date": "2026-03-15",
                        "vix_level": 25.0,
                        "macro_call": "risk-off",
                        "sector_thesis": "Valid prior record",
                        "key_themes": ["inflation"],
                    },
                    {
                        "macro_call": "risk-on",
                        "sector_thesis": "Malformed record",
                        "key_themes": ["earnings"],
                    },
                ]
            ),
            encoding="utf-8",
        )
        m = MacroMemory(fallback_path=bad_path)

        with caplog.at_level(logging.WARNING, logger="tradingagents.memory.macro_memory"):
            records = m.get_recent(limit=5, as_of_date="2026-03-20")
            ctx = m.build_macro_context(limit=5, as_of_date="2026-03-20")

        assert [record["sector_thesis"] for record in records] == ["Valid prior record"]
        assert "Malformed record" not in ctx
        assert "Valid prior record" in ctx
        assert any(
            "corrupt" in r.message.lower()
            or "malformed" in r.message.lower()
            or "unreadable" in r.message.lower()
            for r in caplog.records
        )

    def test_local_as_of_filter_uses_iso_date_prefix_for_timestamp_records(self, tmp_path):
        """Timestamp-shaped local dates are compared by their YYYY-MM-DD prefix."""
        path = tmp_path / "macro.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "regime_date": "2026-03-15T12:00:00",
                        "vix_level": 25.0,
                        "macro_call": "risk-off",
                        "sector_thesis": "Intraday record",
                        "key_themes": [],
                    },
                    {
                        "regime_date": "2026-03-16T00:00:00",
                        "vix_level": 18.0,
                        "macro_call": "risk-on",
                        "sector_thesis": "Future intraday record",
                        "key_themes": [],
                    },
                ]
            ),
            encoding="utf-8",
        )
        m = MacroMemory(fallback_path=path)

        records = m.get_recent(limit=5, as_of_date="2026-03-15")

        assert [record["sector_thesis"] for record in records] == ["Intraday record"]


# ---------------------------------------------------------------------------
# Additional coverage
# ---------------------------------------------------------------------------


def test_macro_call_normalized_to_lowercase(mem):
    """macro_call is stored in lowercase regardless of input casing."""
    mem.record_macro_state("2026-03-26", 20.0, "Risk-Off", "mixed", [])
    records = mem.get_recent()
    assert records[0]["macro_call"] == "risk-off"


def test_vix_stored_as_float(mem):
    """vix_level is always stored as a float."""
    mem.record_macro_state("2026-03-26", 22, "neutral", "flat market", [])
    records = mem.get_recent()
    assert isinstance(records[0]["vix_level"], float)


def test_key_themes_stored_as_list(mem):
    """key_themes is persisted as a list."""
    themes = ["inflation", "rate hikes"]
    mem.record_macro_state("2026-03-26", 20.0, "risk-off", "Fed hawkish", themes)
    records = mem.get_recent()
    assert records[0]["key_themes"] == themes


def test_get_recent_limit_respected(mem):
    """get_recent() returns at most *limit* records."""
    for i in range(5):
        mem.record_macro_state(f"2026-03-{i + 1:02d}", float(i), "neutral", "", [])
    records = mem.get_recent(limit=3)
    assert len(records) == 3


def test_record_outcome_returns_false_for_unknown_date(mem):
    """record_outcome() returns False when no matching date exists."""
    result = mem.record_outcome("9999-01-01", {"correct": True})
    assert result is False


def test_record_outcome_only_fills_null_outcome(mem):
    """record_outcome() will not overwrite a record that already has an outcome."""
    mem.record_macro_state("2026-03-26", 25.0, "risk-off", "test", [])
    mem.record_outcome("2026-03-26", {"correct": True})

    # Second call should return False — outcome already set
    result = mem.record_outcome("2026-03-26", {"correct": False})
    assert result is False

    records = mem.get_recent()
    assert records[0]["outcome"]["correct"] is True


def test_record_macro_state_updates_duplicate_same_date_and_run_id(mem):
    """Local fallback should update an existing same-date/run record instead of appending."""
    mem.record_macro_state("2026-03-26", 20.0, "neutral", "old", [], run_id="run-1")
    mem.record_macro_state("2026-03-26", 25.0, "risk-off", "new", ["rates"], run_id="run-1")

    records = mem.get_recent(limit=5)
    assert len(records) == 1
    assert records[0]["vix_level"] == 25.0
    assert records[0]["macro_call"] == "risk-off"
    assert records[0]["sector_thesis"] == "new"


def test_record_macro_state_preserves_existing_outcome_on_duplicate_rerun(mem):
    """Duplicate same-date/run writes must not erase a back-filled outcome."""
    outcome = {"regime_confirmed": True}
    mem.record_macro_state("2026-03-26", 20.0, "neutral", "old", [], run_id="run-1")
    assert mem.record_outcome("2026-03-26", outcome, run_id="run-1") is True

    mem.record_macro_state("2026-03-26", 25.0, "risk-off", "new", ["rates"], run_id="run-1")

    records = mem.get_recent(limit=5)
    assert len(records) == 1
    assert records[0]["sector_thesis"] == "new"
    assert records[0]["outcome"] == outcome


def test_record_outcome_with_run_id_addresses_matching_pending_record(mem):
    """run_id addressing should update only the matching pending macro state."""
    mem.record_macro_state("2026-03-26", 20.0, "neutral", "first", [], run_id="run-1")
    mem.record_macro_state("2026-03-26", 21.0, "risk-off", "second", [], run_id="run-2")

    assert mem.record_outcome("2026-03-26", {"confirmed": True}, run_id="run-1") is True

    records = sorted(mem.get_recent(limit=5), key=lambda rec: rec["run_id"])
    assert records[0]["outcome"] == {"confirmed": True}
    assert records[1]["outcome"] is None


def test_record_outcome_legacy_date_only_updates_newest_missing_run_id_record(mem):
    """Legacy date-only addressing should only update a newest pending record without run_id."""
    mem.record_macro_state("2026-03-26", 19.0, "neutral", "legacy old", [])
    mem.record_macro_state("2026-03-26", 20.0, "neutral", "first", [], run_id="run-1")
    mem.record_macro_state("2026-03-26", 21.0, "risk-off", "second", [], run_id="run-2")
    mem.record_macro_state("2026-03-26", 22.0, "transition", "legacy new", [])

    assert mem.record_outcome("2026-03-26", {"legacy": True}) is True

    records = mem.get_recent(limit=5)
    updated = [rec for rec in records if rec["outcome"] == {"legacy": True}]
    assert len(updated) == 1
    assert updated[0].get("run_id") == "manual"
    assert updated[0]["sector_thesis"] == "legacy new"
    assert all(
        rec["outcome"] is None for rec in records if rec.get("run_id") not in (None, "manual")
    )


def test_record_outcome_legacy_date_only_does_not_update_run_id_records(mem):
    """Date-only legacy addressing must not update records that carry run_id."""
    mem.record_macro_state("2026-03-26", 20.0, "neutral", "first", [], run_id="run-1")
    mem.record_macro_state("2026-03-26", 21.0, "risk-off", "second", [], run_id="run-2")

    assert mem.record_outcome("2026-03-26", {"legacy": True}) is False

    records = mem.get_recent(limit=5)
    assert all(rec["outcome"] is None for rec in records)


def test_record_macro_state_updates_duplicate_same_date_and_missing_run_id(mem):
    """Local fallback should treat missing run_id as part of the duplicate key."""
    mem.record_macro_state("2026-03-26", 20.0, "neutral", "old", [])
    mem.record_macro_state("2026-03-26", 25.0, "risk-off", "new", ["rates"])

    records = mem.get_recent(limit=5)
    assert len(records) == 1
    assert records[0]["vix_level"] == 25.0
    assert records[0]["macro_call"] == "risk-off"
    assert records[0]["sector_thesis"] == "new"


def test_record_macro_state_mongo_upserts_missing_run_id_key():
    """Mongo writes should upsert by (regime_date, run_id), including run_id=None."""
    updates = []

    class FakeCollection:
        def update_one(self, query, update, upsert=False):
            updates.append((query, update, upsert))

    mem = MacroMemory.__new__(MacroMemory)
    mem._col = FakeCollection()
    mem._fallback_path = None

    mem.record_macro_state("2026-03-26", 20.0, "neutral", "legacy", [])

    assert updates[0][0] == {"regime_date": "2026-03-26", "run_id": "manual"}
    assert updates[0][2] is True
    assert "outcome" not in updates[0][1]["$set"]
    assert updates[0][1]["$setOnInsert"]["outcome"] is None


def test_record_outcome_mongo_legacy_query_excludes_run_id_records():
    """Mongo legacy date-only outcome updates should target only missing/empty run_id records."""
    queries = []

    class FakeCollection:
        def find_one_and_update(self, query, update, sort):
            queries.append(query)
            return None

    mem = MacroMemory.__new__(MacroMemory)
    mem._col = FakeCollection()
    mem._fallback_path = None

    assert mem.record_outcome("2026-03-26", {"legacy": True}) is False

    assert queries[0] == {
        "regime_date": "2026-03-26",
        "outcome": None,
        "$or": [
            {"run_id": {"$exists": False}},
            {"run_id": None},
            {"run_id": ""},
            {"run_id": "manual"},
        ],
    }


def test_get_recent_mongo_uses_as_of_date_query():
    """Mongo get_recent(as_of_date=...) should constrain regime_date."""
    calls = []

    class FakeCursor:
        def __init__(self, docs):
            self.docs = docs

        def sort(self, key, direction):
            calls.append(("sort", key, direction))
            return self

        def limit(self, limit):
            calls.append(("limit", limit))
            return self.docs

    class FakeCollection:
        def find(self, query, projection):
            calls.append(("find", query, projection))
            return FakeCursor([{"regime_date": "2026-03-15"}])

    mem = MacroMemory.__new__(MacroMemory)
    mem._col = FakeCollection()
    mem._fallback_path = None

    records = mem.get_recent(limit=7, as_of_date="2026-03-20")

    assert records == [{"regime_date": "2026-03-15"}]
    assert calls[0] == (
        "find",
        {"regime_date": {"$lte": "2026-03-20"}},
        {"_id": 0},
    )
    assert calls[2] == ("limit", 7)


def test_build_macro_context_no_prior_history_message(mem):
    """build_macro_context() returns informative text when no records exist."""
    ctx = mem.build_macro_context()
    assert "No prior" in ctx


def test_build_macro_context_shows_outcome_pending(mem):
    """build_macro_context() shows 'pending' for records with no outcome."""
    mem.record_macro_state("2026-03-26", 25.0, "risk-off", "test", [])
    ctx = mem.build_macro_context()
    assert "pending" in ctx


def test_build_macro_context_shows_outcome_confirmed(mem):
    """build_macro_context() shows outcome notes when outcome is set."""
    mem.record_macro_state("2026-03-26", 25.0, "risk-off", "test", [])
    mem.record_outcome(
        "2026-03-26",
        {"regime_confirmed": True, "notes": "Bear market held"},
    )
    ctx = mem.build_macro_context()
    assert "Bear market held" in ctx


def test_persistence_across_instances(tmp_path):
    """Records written by one MacroMemory instance are visible to another."""
    fb = tmp_path / "macro.json"

    m1 = MacroMemory(fallback_path=fb)
    m1.record_macro_state("2026-03-26", 25.0, "risk-off", "thesis", ["theme"])

    m2 = MacroMemory(fallback_path=fb)
    records = m2.get_recent()
    assert len(records) == 1


def test_local_file_created_on_first_write(tmp_path):
    """The fallback JSON file is created automatically on first write."""
    fb = tmp_path / "subdir" / "macro.json"
    assert not fb.exists()

    m = MacroMemory(fallback_path=fb)
    m.record_macro_state("2026-03-26", 20.0, "neutral", "test", [])

    assert fb.exists()
    data = json.loads(fb.read_text())
    assert len(data) == 1
