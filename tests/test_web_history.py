"""Run history: manifest round-trip, CLI-era degradation, mtime cache,
report loading with complete_report fallback."""


import pytest

from tradingagents.web.history import RunHistory, load_report, write_manifest

pytestmark = pytest.mark.unit


def _make_web_run(results_dir, ticker="AAPL", date="2026-07-01", decision="BUY"):
    run_dir = results_dir / ticker / date
    (run_dir / "reports").mkdir(parents=True)
    (run_dir / "reports" / "market_report.md").write_text("# market", encoding="utf-8")
    write_manifest(run_dir, {
        "run_id": "abc123",
        "ticker": ticker,
        "date": date,
        "status": "done",
        "decision": decision,
        "provider": "openai",
        "deep_think_llm": "gpt-5.5",
        "quick_think_llm": "gpt-5.4-mini",
        "analysts": ["market"],
        "duration_seconds": 61.0,
    })
    return run_dir


def test_web_run_listed_from_manifest(tmp_path):
    _make_web_run(tmp_path)
    entries = RunHistory(tmp_path).list_runs()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source"] == "web"
    assert entry["decision"] == "BUY"
    assert entry["run_id"] == "abc123"
    assert entry["has_report"] is True


def test_cli_run_degrades_gracefully(tmp_path):
    reports = tmp_path / "TSLA" / "2026-06-15" / "reports"
    reports.mkdir(parents=True)
    (reports / "market_report.md").write_text("x", encoding="utf-8")
    # Non-run directories must be ignored.
    (tmp_path / "TSLA" / "TradingAgentsStrategy_logs").mkdir()

    entries = RunHistory(tmp_path).list_runs()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source"] == "cli"
    assert entry["decision"] is None
    assert entry["ticker"] == "TSLA"


def test_listing_sorted_newest_first(tmp_path):
    _make_web_run(tmp_path, "AAPL", "2026-07-01")
    _make_web_run(tmp_path, "MSFT", "2026-07-03")
    dates = [e["date"] for e in RunHistory(tmp_path).list_runs()]
    assert dates == ["2026-07-03", "2026-07-01"]


def test_cache_serves_unchanged_entries_and_drops_deleted(tmp_path):
    run_dir = _make_web_run(tmp_path)
    history = RunHistory(tmp_path)
    first = history.list_runs()
    # Corrupt the manifest without touching the dir mtime: cache must serve
    # the old entry (keyed on mtime, not content).
    (run_dir / "run.json").write_text("not json", encoding="utf-8")
    import os
    stat = run_dir.stat()
    os.utime(run_dir, (stat.st_atime, stat.st_mtime))
    assert history.list_runs() == first

    # Deleting the run dir drops it from the listing and the cache.
    import shutil
    shutil.rmtree(tmp_path / "AAPL")
    assert history.list_runs() == []


def test_load_report_sections(tmp_path):
    _make_web_run(tmp_path)
    report = load_report(tmp_path, "AAPL", "2026-07-01")
    assert report["sections"]["market_report"] == "# market"
    assert report["manifest"]["decision"] == "BUY"
    assert report["complete_report"] is None


def test_load_report_falls_back_to_complete_report(tmp_path):
    reports = tmp_path / "NVDA" / "2026-05-01" / "reports"
    reports.mkdir(parents=True)
    (reports / "complete_report.md").write_text("# full", encoding="utf-8")
    report = load_report(tmp_path, "NVDA", "2026-05-01")
    assert report["sections"] == {}
    assert report["complete_report"] == "# full"


def test_load_report_missing_run(tmp_path):
    assert load_report(tmp_path, "NOPE", "2026-01-01") is None


def test_unreadable_manifest_degrades_to_cli_entry(tmp_path):
    run_dir = tmp_path / "AAPL" / "2026-07-01"
    (run_dir / "reports").mkdir(parents=True)
    (run_dir / "run.json").write_text("{broken", encoding="utf-8")
    entries = RunHistory(tmp_path).list_runs()
    assert entries[0]["source"] == "cli"
