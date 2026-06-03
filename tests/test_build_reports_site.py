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


@pytest.mark.unit
def test_generated_pages_do_not_end_with_extra_blank_line():
    builder = load_builder()
    run = builder.Run("AAPL", "2026-06-02", "opus", "2026-06-02 10:10:10", "run")
    row = builder.SummaryRow(
        ticker="AAPL",
        report_link="./AAPL/run/complete_report.md",
        rating="Overweight",
        action="Buy",
        current_price=10.0,
        price_target=12.0,
        target_uplift=0.2,
        annualized_uplift=0.4,
        confidence="High",
        horizon="6m",
    )

    home = builder.build_home({"AAPL": [run]}, 1, [row], "20260602")
    hub = builder.build_ticker_hub("AAPL", [run])

    assert home.endswith("\n")
    assert not home.endswith("\n\n")
    assert hub.endswith("\n")
    assert not hub.endswith("\n\n")


@pytest.mark.unit
def test_horizon_months_handles_year_ranges():
    builder = load_builder()

    assert builder.horizon_months("3-5 years") == 48.0
    assert builder.horizon_months("60d") == 60.0 / 30.4375
    assert builder.horizon_months("12+m") == 12.0
    assert builder.horizon_months("1-2 quarters (Q2 earnings is the decision gate)") == 4.5
    assert builder.horizon_months("Through Q2 2026 earnings") == 3.0


@pytest.mark.unit
def test_current_price_parser_handles_remaining_report_phrasings():
    builder = load_builder()

    assert builder.extract_current_price(
        "The stock has since declined sharply again, closing at **$124.22 on May 29**.",
        "",
        "",
    ) == 124.22
    assert builder.extract_current_price(
        "**Last Close (May 29):** $84.44\n",
        "",
        "",
    ) == 84.44
    assert builder.extract_current_price(
        "Last Close: **$87.24** (June 1, 2026)\n",
        "",
        "",
    ) == 87.24
    assert builder.extract_current_price(
        "| **Close Price** | $46.88 | Caution |\n",
        "",
        "",
    ) == 46.88


@pytest.mark.unit
def test_decision_parser_handles_table_style_final_plan():
    builder = load_builder()
    decision = (
        "| Parameter | Decision |\n"
        "|---|---|\n"
        "| **Rating** | **Overweight** |\n"
        "| **Near-term target** | **$487** (January high) |\n"
        "\n"
        "- 200-SMA reclaim fails on a two-session basis within ~60 days\n"
    )

    assert builder.field(decision, "Rating") == "Overweight"
    assert builder.extract_price_target(decision) == 487.0
    assert builder.extract_time_horizon(decision) == "60d"
