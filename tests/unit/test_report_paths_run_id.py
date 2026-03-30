"""Tests for canonical run_id support in report_paths.py."""

from __future__ import annotations

import re
import time as _time
from unittest.mock import patch

from tradingagents import report_paths
from tradingagents.report_paths import (
    generate_run_id,
    get_daily_dir,
    get_digest_path,
    get_eval_dir,
    get_market_dir,
    get_ticker_dir,
    ts_now,
)


def test_generate_run_id_returns_ulid():
    rid = generate_run_id()
    assert len(rid) == 26
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", rid)


def test_generate_run_id_is_unique():
    ids = {generate_run_id() for _ in range(100)}
    assert len(ids) == 100


def test_get_daily_dir_without_run_id(tmp_path):
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_daily_dir("2026-03-20")
    assert result == tmp_path / "daily" / "2026-03-20"


def test_get_daily_dir_with_run_id(tmp_path):
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_daily_dir("2026-03-20", run_id="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert result == tmp_path / "daily" / "2026-03-20" / "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def test_nested_path_helpers_use_run_id_directory(tmp_path):
    run_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        assert get_market_dir("2026-03-20", run_id) == tmp_path / "daily" / "2026-03-20" / run_id / "market"
        assert get_ticker_dir("2026-03-20", "AAPL", run_id) == tmp_path / "daily" / "2026-03-20" / run_id / "AAPL"
        assert get_eval_dir("2026-03-20", "AAPL", run_id) == tmp_path / "daily" / "2026-03-20" / run_id / "AAPL" / "eval"


def test_get_digest_path_stays_at_date_level(tmp_path):
    with patch.object(report_paths, "REPORTS_ROOT", tmp_path):
        result = get_digest_path("2026-03-20")
    assert result == tmp_path / "daily" / "2026-03-20" / "daily_digest.md"


def test_ts_now_format_and_sortability():
    t1 = ts_now()
    _time.sleep(0.002)
    t2 = ts_now()
    assert len(t1) == 19
    assert t1.endswith("Z")
    assert "T" in t1
    assert t2 >= t1
