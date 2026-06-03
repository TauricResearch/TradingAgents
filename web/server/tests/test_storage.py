"""Unit tests for ``web.server.storage`` primitives."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from web.server import storage


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    storage.init_settings(data_dir=str(data), cache_dir=str(cache))
    return data, cache


def test_write_json_atomic_overwrites_existing_file(tmp_path, data_root):
    target = tmp_path / "config.json"
    storage.write_json_atomic(target, {"v": 1})
    with open(target, "r", encoding="utf-8") as reader:
        reader.read()
    storage.write_json_atomic(target, {"v": 2})
    assert storage.read_json(target) == {"v": 2}


def test_write_json_atomic_replaces_partial_files_atomically(tmp_path, data_root):
    target = tmp_path / "x.json"
    storage.write_json_atomic(target, {"a": 1, "b": [1, 2, 3]})
    raw = target.read_text(encoding="utf-8")
    assert "\n" in raw  # indented
    parsed = json.loads(raw)
    assert parsed == {"a": 1, "b": [1, 2, 3]}


def test_write_json_atomic_creates_parent_dirs(tmp_path, data_root):
    target = tmp_path / "nested" / "deeper" / "x.json"
    storage.write_json_atomic(target, {"ok": True})
    assert storage.read_json(target) == {"ok": True}


def test_read_json_returns_none_for_missing(tmp_path, data_root):
    assert storage.read_json(tmp_path / "absent.json") is None


def test_read_json_returns_none_for_malformed(tmp_path, data_root):
    p = tmp_path / "broken.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert storage.read_json(p) is None


def test_append_jsonl_produces_valid_lines(tmp_path, data_root):
    p = tmp_path / "events.jsonl"
    storage.append_jsonl(p, {"a": 1})
    storage.append_jsonl(p, {"a": 2})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"a": 2}


def test_read_jsonl_skips_truncated_last_line(tmp_path, data_root):
    """A crash mid-write leaves a partial last line. read_jsonl must
    not raise and must skip the bad line while preserving earlier ones."""
    p = tmp_path / "events.jsonl"
    storage.append_jsonl(p, {"a": 1})
    storage.append_jsonl(p, {"a": 2})
    raw = p.read_text(encoding="utf-8")
    p.write_text(raw + '{"a": 3, "b":', encoding="utf-8")
    out = storage.read_jsonl(p)
    assert out == [{"a": 1}, {"a": 2}]


def test_read_jsonl_empty_when_file_missing(tmp_path, data_root):
    assert storage.read_jsonl(tmp_path / "absent.jsonl") == []


def test_slug_for_now_uses_israel_timezone_in_summer():
    """July is IDT (DST in effect)."""
    dt_utc = datetime(2026, 7, 15, 11, 0, 0, tzinfo=timezone.utc)  # 14:00 Israel
    assert storage.slug_for_now(dt_utc) == "2026-07-15_14-00-00_IDT"


def test_slug_for_now_uses_israel_timezone_in_winter():
    """January is IST (no DST)."""
    dt_utc = datetime(2026, 1, 15, 11, 0, 0, tzinfo=timezone.utc)  # 13:00 Israel
    assert storage.slug_for_now(dt_utc) == "2026-01-15_13-00-00_IST"


def test_utc_iso_uses_z_suffix():
    dt = datetime(2026, 6, 3, 11, 30, 0, 123456, tzinfo=timezone.utc)
    assert storage.utc_iso(dt) == "2026-06-03T11:30:00.123456Z"


def test_utc_iso_handles_naive_datetime():
    """A tz-less datetime is assumed UTC."""
    dt = datetime(2026, 6, 3, 11, 30, 0)
    assert storage.utc_iso(dt).endswith("Z")


def test_clear_ticker_data_removes_both_data_dir_and_checkpoint(tmp_path, data_root):
    data, cache = data_root
    (data / "NVDA" / "2026-06-03_14-30-00_IDT").mkdir(parents=True)
    (data / "NVDA" / "2026-06-03_14-30-00_IDT" / "run.json").write_text("{}")
    (cache / "checkpoints").mkdir(parents=True, exist_ok=True)
    (cache / "checkpoints" / "NVDA.db").write_text("")

    storage.clear_ticker_data("NVDA")

    assert not (data / "NVDA").exists()
    assert not (cache / "checkpoints" / "NVDA.db").exists()


def test_clear_ticker_data_is_noop_when_missing(tmp_path, data_root):
    """If neither the data dir nor the checkpoint file exists, clear_ticker_data
    is a no-op and does not raise.
    """
    storage.clear_ticker_data("ZZZZ")  # should not raise
    assert not (data_root[0] / "ZZZZ").exists()


def test_clear_ticker_data_handles_partial_existence(tmp_path, data_root):
    """Works whether one of the two targets is missing or both exist."""
    data, cache = data_root
    # Only data dir, no checkpoint
    (data / "AAPL" / "run1").mkdir(parents=True)
    storage.clear_ticker_data("AAPL")
    assert not (data / "AAPL").exists()
    # Only checkpoint, no data dir
    (cache / "checkpoints").mkdir(parents=True, exist_ok=True)
    (cache / "checkpoints" / "MSFT.db").touch()
    storage.clear_ticker_data("MSFT")
    assert not (cache / "checkpoints" / "MSFT.db").exists()
