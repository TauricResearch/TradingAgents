"""Unit tests for ``web.server.queries``."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from web.server import queries, storage


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    storage.init_settings(data_dir=str(data), cache_dir=str(cache))
    return data


def test_watchlist_starts_empty(data_root):
    assert queries.read_watchlist() == []


def test_add_ticker_creates_row(data_root):
    row = queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")
    assert row["ticker"] == "NVDA"
    assert row["company_name"] == "NVIDIA"
    assert row["exchange"] == "NASDAQ"
    assert queries.read_watchlist() == [row]


def test_add_ticker_uppercases_ticker(data_root):
    queries.add_ticker("nvda", "NVIDIA", "NASDAQ")
    rows = queries.read_watchlist()
    assert rows[0]["ticker"] == "NVDA"


def test_add_duplicate_ticker_raises(data_root):
    queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")
    with pytest.raises(queries.DuplicateTicker):
        queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")


def test_add_ticker_creates_data_dir(data_root, tmp_path):
    queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")
    assert (tmp_path / "data" / "NVDA").is_dir()


def test_remove_ticker_clears_data(data_root, tmp_path):
    queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")
    rd = tmp_path / "data" / "NVDA" / "2026-06-03_14-30-00_IDT"
    rd.mkdir(parents=True)
    (rd / "run.json").write_text("{}")
    queries.remove_ticker("NVDA")
    assert queries.read_watchlist() == []
    assert not (tmp_path / "data" / "NVDA").exists()


def test_remove_ticker_unknown_is_noop(data_root):
    queries.remove_ticker("ZZZZ")  # must not raise
    assert queries.read_watchlist() == []


def test_update_last_decision_sets_fields(data_root):
    queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")
    queries.update_last_decision(
        "NVDA", "NVDA:2026-06-03T11:30:00.000000Z", "BUY @ 260.0", datetime(2026, 6, 3, 11, 35, tzinfo=timezone.utc)
    )
    rows = queries.read_watchlist()
    assert rows[0]["last_run_id"] == "NVDA:2026-06-03T11:30:00.000000Z"
    assert rows[0]["last_decision"] == "BUY @ 260.0"
    assert rows[0]["last_decision_at"] == "2026-06-03T11:35:00.000000Z"


def test_update_last_decision_for_missing_ticker_is_noop(data_root):
    queries.update_last_decision("ZZZZ", "r", "x", datetime.now(timezone.utc))
    assert queries.read_watchlist() == []


def test_run_to_dict_passes_through_fields():
    raw = {
        "id": "NVDA:2026-06-03T11:30:00.000000Z",
        "ticker": "NVDA",
        "slug": "2026-06-03_14-30-00_IDT",
        "started_at": "2026-06-03T11:30:00.000000Z",
        "finished_at": "2026-06-03T11:35:00.000000Z",
        "status": "done",
        "decision_action": "BUY",
        "decision_target": 260.0,
        "decision_rationale": "ok",
        "decision_confidence": 0.8,
    }
    assert queries.run_to_dict(raw) == raw


def test_event_to_dict_keeps_run_id():
    e = {"id": 1, "type": "analyst_thinking", "ts": "2026-06-03T11:30:00.000000Z", "data": {"x": 1}}
    out = queries.event_to_dict(e, "NVDA:r")
    assert out["run_id"] == "NVDA:r"
    assert out["data"] == {"x": 1}
