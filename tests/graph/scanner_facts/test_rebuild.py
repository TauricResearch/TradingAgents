"""Tests for rebuild.py — historical artifact rebuild API and CLI.

All tests use tmp_path or fixture dirs — never real reports/.
"""
import shutil
from pathlib import Path

import pytest

from tradingagents.graph.scanner_facts.builder import load_scanner_graph_facts
from tradingagents.graph.scanner_facts.rebuild import rebuild_scanner_graph_facts
from tradingagents.graph.scanner_facts.schema import validate_graph_facts

FIXTURES = Path(__file__).parent / "fixtures"


# ---- helper: copy fixture dir to tmp ----

def _make_tmp_market_dir(tmp_path: Path) -> Path:
    """Copy real fixtures into a temp market dir structure."""
    market = tmp_path / "reports" / "daily" / "2026-04-16" / "TESTRUN" / "market"
    market.mkdir(parents=True)
    for f in FIXTURES.iterdir():
        if f.is_file():
            shutil.copy(f, market / f.name)
    return market


# ---- basic rebuild ----

def test_rebuild_creates_artifact(tmp_path):
    _make_tmp_market_dir(tmp_path)
    path = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    assert path.exists()
    assert path.name == "scanner_graph_facts.json"


def test_rebuild_artifact_schema_valid(tmp_path):
    _make_tmp_market_dir(tmp_path)
    path = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    facts = load_scanner_graph_facts(path)
    errors = validate_graph_facts(facts)
    assert errors == [], f"Schema errors: {errors}"


def test_rebuild_overwrites_existing(tmp_path):
    _make_tmp_market_dir(tmp_path)
    path1 = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    mtime1 = path1.stat().st_mtime

    import time
    time.sleep(0.05)  # ensure mtime changes if file is rewritten

    path2 = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    assert path1 == path2
    # File should have been rewritten
    assert path2.stat().st_mtime >= mtime1


def test_rebuild_no_overwrite_flag(tmp_path):
    _make_tmp_market_dir(tmp_path)
    path = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    mtime = path.stat().st_mtime

    import time
    time.sleep(0.05)

    rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
        overwrite=False,
    )
    assert path.stat().st_mtime == mtime  # not rewritten


def test_rebuild_contains_real_tickers(tmp_path):
    _make_tmp_market_dir(tmp_path)
    path = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    facts = load_scanner_graph_facts(path)
    ids = {n["id"] for n in facts["nodes"]}
    assert "ON" in ids
    assert "Technology" in ids


# ---- error cases ----

def test_rebuild_missing_market_dir_raises(tmp_path):
    with pytest.raises((FileNotFoundError, Exception)):
        rebuild_scanner_graph_facts(
            "2026-04-16", "NORUN",
            reports_root=tmp_path / "reports",
        )


def test_rebuild_missing_macro_json_raises(tmp_path):
    market = _make_tmp_market_dir(tmp_path)
    (market / "macro_scan_summary.json").unlink()
    with pytest.raises(FileNotFoundError):
        rebuild_scanner_graph_facts(
            "2026-04-16", "TESTRUN",
            reports_root=tmp_path / "reports",
        )


# ---- degraded fallback: malformed JSON ----

def test_rebuild_malformed_macro_json_with_md_fallback(tmp_path):
    """If macro_scan_summary.json is malformed but Markdown summaries exist, rebuild proceeds."""
    market = _make_tmp_market_dir(tmp_path)
    (market / "macro_scan_summary.json").write_text("{ not valid json }")

    path = rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN",
        reports_root=tmp_path / "reports",
    )
    facts = load_scanner_graph_facts(path)
    assert facts["metadata"].get("degraded_source") == "macro_json_malformed"
    # Markdown-sourced tickers should still be present
    ids = {n["id"] for n in facts["nodes"]}
    assert len(ids) > 0, "Expected nodes from markdown fallback"


def test_rebuild_malformed_macro_json_no_md_raises(tmp_path):
    """If both macro JSON is malformed AND no usable Markdown summaries: fail loudly."""
    market = tmp_path / "reports" / "daily" / "2026-04-16" / "TESTRUN" / "market"
    market.mkdir(parents=True)
    (market / "macro_scan_summary.json").write_text("{ not valid json }")
    # No markdown files at all → nothing to fall back to
    with pytest.raises((ValueError, FileNotFoundError)):
        rebuild_scanner_graph_facts(
            "2026-04-16", "TESTRUN",
            reports_root=tmp_path / "reports",
        )


# ---- CLI ----

def test_cli_invocation(tmp_path):
    """Invoke rebuild CLI as __main__ module using subprocess."""
    import subprocess
    import sys

    _make_tmp_market_dir(tmp_path)
    result = subprocess.run(
        [
            sys.executable, "-m",
            "tradingagents.graph.scanner_facts.rebuild",
            "--date", "2026-04-16",
            "--run-id", "TESTRUN",
            "--reports-root", str(tmp_path / "reports"),
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent.parent.parent),  # repo root
    )
    assert result.returncode == 0, f"CLI failed:\n{result.stderr}"
    artifact = (
        tmp_path / "reports" / "daily" / "2026-04-16" / "TESTRUN"
        / "market" / "scanner_graph_facts.json"
    )
    assert artifact.exists()


def test_cli_no_overwrite_flag(tmp_path):
    """--no-overwrite flag prevents rewrite of existing artifact."""
    import subprocess
    import sys

    market = _make_tmp_market_dir(tmp_path)
    # First build
    rebuild_scanner_graph_facts(
        "2026-04-16", "TESTRUN", reports_root=tmp_path / "reports"
    )
    artifact = market / "scanner_graph_facts.json"
    mtime = artifact.stat().st_mtime

    import time
    time.sleep(0.05)

    result = subprocess.run(
        [
            sys.executable, "-m",
            "tradingagents.graph.scanner_facts.rebuild",
            "--date", "2026-04-16",
            "--run-id", "TESTRUN",
            "--reports-root", str(tmp_path / "reports"),
            "--no-overwrite",
        ],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent.parent.parent),
    )
    assert result.returncode == 0
    assert artifact.stat().st_mtime == mtime
