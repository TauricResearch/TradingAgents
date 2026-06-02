from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def load_builder():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_reports_site.py"
    spec = importlib.util.spec_from_file_location("build_reports_site", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_latest_runs_can_filter_to_analysis_date():
    builder = load_builder()
    runs = {
        "AAPL": [
            builder.Run("AAPL", "2026-06-01", "opus", "2026-06-01 20:12:03", "aapl-0601"),
            builder.Run("AAPL", "2026-06-02", "opus", "2026-06-02 11:01:33", "aapl-0602"),
        ],
        "QCOM": [
            builder.Run("QCOM", "2026-06-01", "opus", "2026-06-02 00:08:03", "qcom-early"),
            builder.Run("QCOM", "2026-06-01", "opus", "2026-06-02 09:28:30", "qcom-late"),
        ],
    }

    selected = builder.latest_runs(runs, analysis_date="20260601")

    assert {run.ticker: run.folder_name for run in selected} == {
        "AAPL": "aapl-0601",
        "QCOM": "qcom-late",
    }


@pytest.mark.unit
def test_replace_decision_summary_leaves_other_homepage_sections():
    builder = load_builder()
    home = (
        "# TradingAgents Reports\n"
        "\n"
        "_95 runs across 44 tickers._\n"
        "\n"
        "## Latest Decision Summary\n"
        "\n"
        "old table\n"
        "\n"
        "## Regeneration Skill\n"
        "\n"
        "regen text\n"
        "\n"
        "## Tickers\n"
        "\n"
        "- [AAPL](AAPL/index.md) &middot; 3 runs\n"
    )

    out = builder.replace_decision_summary(
        home,
        ["## 2026-06-01 Decision Summary", "", "new table", ""],
    )

    assert "_95 runs across 44 tickers._" in out
    assert "old table" not in out
    assert "new table" in out
    assert "## Regeneration Skill\n\nregen text" in out
    assert "## Tickers\n\n- [AAPL](AAPL/index.md) &middot; 3 runs" in out
