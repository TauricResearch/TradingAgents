"""Tests for the `tradingagents run-past` CLI subcommand."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from cli.main import app
from web.server import background_runs


@pytest.fixture
def isolated_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path / "data")
    return tmp_path / "data"


def test_run_past_list_empty(isolated_data_root):
    runner = CliRunner()
    result = runner.invoke(app, ["run-past", "list"])
    assert result.exit_code == 0
    assert "(no jobs)" in result.stdout or "Job ID" in result.stdout


def test_run_past_status_via_typer(isolated_data_root, monkeypatch):
    monkeypatch.setattr(background_runs, "_call_propagate",
                        lambda t, d: {"ticker": t, "trade_date": d})
    runner = CliRunner()
    job_id = background_runs.start("NVDA", "2024-05-06", "2024-05-06", "1d", 1)
    handle = background_runs.get_handle(job_id)
    if handle and handle.thread:
        handle.thread.join(timeout=5.0)
    result = runner.invoke(app, ["run-past", "status", job_id])
    assert result.exit_code == 0
    assert job_id in result.stdout
    assert "ticker:" in result.stdout


def test_run_past_cancel_via_typer(isolated_data_root, monkeypatch):
    monkeypatch.setattr(background_runs, "_call_propagate",
                        lambda t, d: {"ticker": t, "trade_date": d})
    runner = CliRunner()
    job_id = background_runs.start("NVDA", "2024-05-06", "2024-05-06", "1d", 1)
    result = runner.invoke(app, ["run-past", "cancel", job_id])
    assert result.exit_code == 0
