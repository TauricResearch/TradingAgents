import zipfile
from datetime import datetime, timezone

import pytest

from web.server import storage
from web.server.download import generate_summary_csv, generate_ticker_zip


# define fixtures inline to avoid conftest import ordering issues
@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """Per-test data dir under tmp_path."""
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(data))
    monkeypatch.setenv("TRADINGAGENTS_CACHE_DIR", str(cache))
    monkeypatch.setenv("TRADINGAGENTS_DASHBOARD_DISABLE_PRICE_FEED", "1")
    storage.init_settings(data_dir=str(data), cache_dir=str(cache))
    return data


def test_generate_summary_csv_empty(data_root):
    """Ticker with no runs → CSV with only headers."""
    csv_text = generate_summary_csv("FAKE")
    lines = [line for line in csv_text.strip().split("\n") if line]
    assert lines[0].split(",")[0] == "run_id"
    assert len(lines) == 1


def test_generate_summary_csv_with_data(data_root):
    """Multiple runs → correct CSV rows in order."""
    # Create two runs for AAPL
    run1 = storage.create_run_dir("AAPL", started_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc))
    run2 = storage.create_run_dir("AAPL", started_at=datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc))

    # Simulate completed run1
    r1 = storage.read_run(run1["run_id"])
    r1["status"] = "done"
    r1["decision_action"] = "BUY"
    r1["decision_target"] = 150.0
    r1["decision_confidence"] = 0.85
    r1["llm_provider"] = "openai"
    r1["deep_think_model"] = "gpt-5.5"
    r1["start_price"] = 145.0
    r1["total_duration_s"] = 120.5
    storage.write_json_atomic(run1["run_dir"] / "run.json", r1)

    # Simulate running run2 (no finish)
    r2 = storage.read_run(run2["run_id"])
    r2["status"] = "running"
    storage.write_json_atomic(run2["run_dir"] / "run.json", r2)

    csv_text = generate_summary_csv("AAPL")
    lines = [line for line in csv_text.strip().split("\n") if line]
    assert len(lines) == 3  # header + 2 rows
    # Row 1 (newest first – list_ticker_runs is newest first)
    assert "AAPL:2024-01-02T10:00:00" in lines[1]
    assert "running" in lines[1]
    # Row 2 (older)
    assert "AAPL:2024-01-01T10:00:00" in lines[2]
    assert "BUY" in lines[2]
    assert "openai" in lines[2]
    assert "145.0" in lines[2]
    assert "120.5" in lines[2]


def test_generate_ticker_zip(data_root):
    """ZIP contains run directories, events, stages and summary.csv."""
    run = storage.create_run_dir("MSFT", started_at=datetime(2024, 3, 1, 9, 0, 0, tzinfo=timezone.utc))
    storage.append_run_event(run["run_id"], {"type": "test", "data": {}})
    (run["run_dir"] / "stages" / "market.json").write_text('{"node": "Market Analyst"}')

    buf = generate_ticker_zip("MSFT")
    z = zipfile.ZipFile(buf)
    names = z.namelist()
    # Must contain summary.csv
    assert any(n == "summary.csv" for n in names)
    # Must contain run directories
    assert any("2024-03-01" in n for n in names)
    # Must contain events
    assert any("events.jsonl" in n for n in names)
    # Must contain stages
    assert any("market.json" in n for n in names)
