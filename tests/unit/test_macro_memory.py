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
