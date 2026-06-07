from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cli.main import save_report_to_disk
from tradingagents.dataflows.india.symbols import IndiaSymbolError


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_report_writer_rejects_unsafe_ticker_before_creating_output_dir(tmp_path):
    target = tmp_path / "unsafe-output"

    with pytest.raises(IndiaSymbolError):
        save_report_to_disk({"trade_date": "2026-06-05"}, "../RELIANCE", target)

    assert not target.exists()


@pytest.mark.unit
def test_no_tracked_generated_reports_filings_or_bytecode():
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    tracked = result.stdout.splitlines()
    forbidden = [
        path
        for path in tracked
        if path.startswith("reports/")
        or path.startswith("data/india/filings/")
        or path.startswith("data/india/manual/")
        or path.endswith(".pyc")
        or "/__pycache__/" in path
        or path.endswith(".pdf")
        or path.endswith(".sqlite")
        or path.endswith(".db")
        or path.endswith(".log")
    ]

    assert forbidden == []


@pytest.mark.unit
def test_user_facing_docs_do_not_advertise_order_execution():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    india_readme = (REPO_ROOT / "README_INDIA.md").read_text(encoding="utf-8")
    dashboard = (REPO_ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    combined = "\n".join([readme, india_readme, dashboard])

    assert "sent to the simulated exchange and executed" not in combined
    assert "KiteConnect" not in combined
    assert "place_order" not in combined
    assert "does not place orders" in combined
    assert "No broker connections, order placement, or live trading controls" in combined


@pytest.mark.unit
def test_gitignore_protects_local_sensitive_artifact_folders():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "reports/" in gitignore
    assert ".env.enterprise" in gitignore
    assert ".streamlit/secrets.toml" in gitignore
    assert "data/india/filings/" in gitignore
    assert "data/india/manual/" in gitignore
