"""Tests for FinancialSituationMemory persistence (issue #563)."""

import json
import pytest
from pathlib import Path

from tradingagents.agents.utils.memory import FinancialSituationMemory


@pytest.fixture
def persist_dir(tmp_path):
    return str(tmp_path / "memory")


def make_config(persist_dir):
    return {"memory_persist_dir": persist_dir}


# ---------------------------------------------------------------------------
# Persistence: data survives a fresh instance
# ---------------------------------------------------------------------------

def test_data_survives_restart(persist_dir):
    """Documents and recommendations loaded by a new instance after save."""
    m1 = FinancialSituationMemory("test", make_config(persist_dir))
    m1.add_situations([("situation A", "recommendation A")])

    m2 = FinancialSituationMemory("test", make_config(persist_dir))
    assert m2.documents == ["situation A"]
    assert m2.recommendations == ["recommendation A"]


def test_multiple_entries_survive_restart(persist_dir):
    """All entries are preserved across instances."""
    m1 = FinancialSituationMemory("test", make_config(persist_dir))
    m1.add_situations([
        ("situation A", "rec A"),
        ("situation B", "rec B"),
    ])

    m2 = FinancialSituationMemory("test", make_config(persist_dir))
    assert len(m2.documents) == 2
    assert len(m2.recommendations) == 2


def test_bm25_index_rebuilt_on_load(persist_dir):
    """BM25 index is functional after loading from disk."""
    m1 = FinancialSituationMemory("test", make_config(persist_dir))
    m1.add_situations([("rising interest rates inflation", "reduce duration")])

    m2 = FinancialSituationMemory("test", make_config(persist_dir))
    results = m2.get_memories("inflation rate rising", n_matches=1)
    assert len(results) == 1
    assert results[0]["recommendation"] == "reduce duration"


# ---------------------------------------------------------------------------
# RAM-only mode: no persist_dir → no file written
# ---------------------------------------------------------------------------

def test_no_persist_dir_no_file(tmp_path):
    """When memory_persist_dir is absent, no persist path is set and data stays in RAM."""
    m = FinancialSituationMemory("test", config={})
    m.add_situations([("situation", "rec")])
    assert m._persist_path is None
    # Data is still accessible in RAM
    assert m.documents == ["situation"]
    assert m.recommendations == ["rec"]
    # Nothing was written to disk
    assert list(tmp_path.iterdir()) == []


def test_none_config_no_file(tmp_path):
    """When config is None (default), no persist path is set and data stays in RAM."""
    m = FinancialSituationMemory("test")
    m.add_situations([("situation", "rec")])
    assert m._persist_path is None
    # Data is still accessible in RAM
    assert m.documents == ["situation"]
    assert m.recommendations == ["rec"]
    # Nothing was written to disk
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Instance isolation: separate names → separate files
# ---------------------------------------------------------------------------

def test_separate_names_separate_files(persist_dir):
    """Two instances with different names do not share state."""
    bull = FinancialSituationMemory("bull_memory", make_config(persist_dir))
    bear = FinancialSituationMemory("bear_memory", make_config(persist_dir))

    bull.add_situations([("bull situation", "buy")])
    bear.add_situations([("bear situation", "sell")])

    bull2 = FinancialSituationMemory("bull_memory", make_config(persist_dir))
    bear2 = FinancialSituationMemory("bear_memory", make_config(persist_dir))

    assert bull2.documents == ["bull situation"]
    assert bear2.documents == ["bear situation"]

    files = {f.name for f in Path(persist_dir).iterdir()}
    assert "bull_memory.json" in files
    assert "bear_memory.json" in files


# ---------------------------------------------------------------------------
# clear() persists the empty state
# ---------------------------------------------------------------------------

def test_clear_persists(persist_dir):
    """After clear(), a new instance starts empty rather than reloading old data."""
    m1 = FinancialSituationMemory("test", make_config(persist_dir))
    m1.add_situations([("situation", "rec")])
    m1.clear()

    m2 = FinancialSituationMemory("test", make_config(persist_dir))
    assert m2.documents == []
    assert m2.bm25 is None


# ---------------------------------------------------------------------------
# Resilience: corrupt or mismatched files fall back to empty memory
# ---------------------------------------------------------------------------

def test_corrupt_json_falls_back_to_empty(persist_dir):
    """A corrupt JSON file is ignored and memory starts empty (no crash)."""
    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    (Path(persist_dir) / "test.json").write_text("not valid json", encoding="utf-8")

    m = FinancialSituationMemory("test", make_config(persist_dir))
    assert m.documents == []
    assert m.bm25 is None


def test_mismatched_lengths_falls_back_to_empty(persist_dir):
    """A file with mismatched documents/recommendations lengths is ignored."""
    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    (Path(persist_dir) / "test.json").write_text(
        json.dumps({"documents": ["a", "b"], "recommendations": ["r1"]}),
        encoding="utf-8",
    )

    m = FinancialSituationMemory("test", make_config(persist_dir))
    assert m.documents == []
    assert m.bm25 is None


# ---------------------------------------------------------------------------
# File format: JSON is human-readable and well-formed
# ---------------------------------------------------------------------------

def test_file_is_valid_json(persist_dir):
    """The persisted file is valid JSON with expected top-level keys."""
    m = FinancialSituationMemory("test", make_config(persist_dir))
    m.add_situations([("situation", "rec")])

    file_path = Path(persist_dir) / "test.json"
    assert file_path.exists()
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "documents" in data
    assert "recommendations" in data
    assert isinstance(data["documents"], list)
    assert isinstance(data["recommendations"], list)
