import json
import pytest
from pathlib import Path
from tradingagents.portfolio.lesson_store import LessonStore

@pytest.fixture
def tmp_store(tmp_path):
    store = LessonStore(tmp_path / "test_lessons.json")
    yield store
    store.clear()

def test_append_to_empty(tmp_store):
    lessons = [
        {"ticker": "NVDA", "scan_date": "2025-12-27", "horizon_days": 30, "sentiment": "negative"},
        {"ticker": "AAPL", "scan_date": "2025-12-27", "horizon_days": 30, "sentiment": "positive"},
    ]
    added = tmp_store.append(lessons)
    assert added == 2
    loaded = tmp_store.load_all()
    assert len(loaded) == 2
    assert loaded[0]["ticker"] == "NVDA"

def test_deduplication(tmp_store):
    lesson1 = {"ticker": "NVDA", "scan_date": "2025-12-27", "horizon_days": 30, "sentiment": "negative"}
    lesson2 = {"ticker": "NVDA", "scan_date": "2025-12-27", "horizon_days": 30, "sentiment": "positive"}  # same dedup key

    added1 = tmp_store.append([lesson1])
    assert added1 == 1
    added2 = tmp_store.append([lesson2])
    assert added2 == 0

    loaded = tmp_store.load_all()
    assert len(loaded) == 1
    assert loaded[0]["sentiment"] == "negative"

def test_load_missing_file(tmp_store):
    assert tmp_store.load_all() == []

def test_atomic_write(tmp_store):
    tmp_store.append([{"ticker": "NVDA", "scan_date": "2025-12-27", "horizon_days": 30}])
    assert tmp_store.path.exists()
    assert not tmp_store.path.with_suffix('.tmp').exists()

def test_append_to_existing(tmp_store):
    tmp_store.append([{"ticker": "NVDA", "scan_date": "2025-12-27", "horizon_days": 30}])
    added = tmp_store.append([{"ticker": "AAPL", "scan_date": "2025-12-27", "horizon_days": 30}])
    assert added == 1
    assert len(tmp_store.load_all()) == 2
