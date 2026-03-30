"""Tests for ReportStore canonical run_id layout."""

from __future__ import annotations

import json
import time

import pytest

from tradingagents.portfolio.exceptions import ReportStoreError
from tradingagents.portfolio.report_store import ReportStore


@pytest.fixture
def tmp_reports(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    return reports_dir


def test_run_id_property():
    store = ReportStore(run_id="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert store.run_id == "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def test_save_scan_uses_run_scoped_timestamped_path(tmp_reports):
    store = ReportStore(base_dir=tmp_reports, run_id="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    path = store.save_scan("2026-03-20", {"watchlist": ["AAPL"]})

    assert "01ARZ3NDEKTSV4RRFFQ69G5FAV/market/report" in str(path)
    assert path.name.endswith("_macro_scan_summary.json")
    assert json.loads(path.read_text())["watchlist"] == ["AAPL"]


def test_save_analysis_uses_run_scoped_timestamped_path(tmp_reports):
    store = ReportStore(base_dir=tmp_reports, run_id="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    path = store.save_analysis("2026-03-20", "AAPL", {"score": 0.9})

    assert "01ARZ3NDEKTSV4RRFFQ69G5FAV/AAPL/report" in str(path)
    assert path.name.endswith("_complete_report.json")


def test_load_scan_returns_latest_version_within_run(tmp_reports):
    store = ReportStore(base_dir=tmp_reports, run_id="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    store.save_scan("2026-03-20", {"version": 1})
    time.sleep(0.002)
    store.save_scan("2026-03-20", {"version": 2})

    assert store.load_scan("2026-03-20") == {"version": 2}


def test_reader_without_run_id_reads_latest_across_runs(tmp_reports):
    store1 = ReportStore(base_dir=tmp_reports, run_id="01ARZ3NDEKTSV4RRFFQ69G5FAA")
    store1.save_scan("2026-03-20", {"run": 1})
    time.sleep(0.002)
    store2 = ReportStore(base_dir=tmp_reports, run_id="01ARZ3NDEKTSV4RRFFQ69G5FAB")
    store2.save_scan("2026-03-20", {"run": 2})

    reader = ReportStore(base_dir=tmp_reports)
    assert reader.load_scan("2026-03-20") == {"run": 2}


def test_save_and_load_run_events(tmp_reports):
    store = ReportStore(base_dir=tmp_reports, run_id="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    events = [{"type": "log", "message": "hello"}, {"type": "result", "message": "done"}]
    store.save_run_events("2026-03-20", events)

    assert store.load_run_events("2026-03-20") == events


def test_writes_require_run_id(tmp_reports):
    store = ReportStore(base_dir=tmp_reports)

    with pytest.raises(ReportStoreError, match="run_id is required"):
        store.save_scan("2026-03-20", {"watchlist": ["AAPL"]})


def test_clear_portfolio_stage_deletes_matching_timestamped_files(tmp_reports):
    store = ReportStore(base_dir=tmp_reports, run_id="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    store.save_pm_decision("2026-03-20", "pid-1", {"buys": ["AAPL"]}, markdown="decision")
    store.save_execution_result("2026-03-20", "pid-1", {"trades": 1})

    deleted = store.clear_portfolio_stage("2026-03-20", "pid-1")
    assert any(name.endswith("pid-1_pm_decision.json") for name in deleted)
    assert any(name.endswith("pid-1_execution_result.json") for name in deleted)


def test_list_analyses_for_date_returns_unique_tickers(tmp_reports):
    store1 = ReportStore(base_dir=tmp_reports, run_id="01ARZ3NDEKTSV4RRFFQ69G5FAA")
    store2 = ReportStore(base_dir=tmp_reports, run_id="01ARZ3NDEKTSV4RRFFQ69G5FAB")
    store1.save_analysis("2026-03-20", "AAPL", {"score": 1})
    store2.save_analysis("2026-03-20", "AAPL", {"score": 2})
    store2.save_analysis("2026-03-20", "MSFT", {"score": 3})

    reader = ReportStore(base_dir=tmp_reports)
    assert reader.list_analyses_for_date("2026-03-20") == ["AAPL", "MSFT"]
