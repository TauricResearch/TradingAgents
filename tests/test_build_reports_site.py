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


def summary_row(
    builder,
    ticker: str,
    folder: str,
    action: str = "Buy",
    model: str = "opus",
):
    return builder.SummaryRow(
        ticker=ticker,
        model=model,
        report_link=f"./{ticker}/{folder}/complete_report.md",
        rating="Overweight",
        action=action,
        current_price=10.0,
        price_target=12.0,
        target_uplift=0.2,
        annualized_uplift=0.4,
        confidence="High",
        horizon="6m",
    )


@pytest.mark.unit
def test_latest_runs_can_filter_to_analysis_date_and_keeps_model_variants():
    builder = load_builder()
    runs = {
        "AAPL": [
            builder.Run("AAPL", "2026-06-01", "opus", "2026-06-01 20:12:03", "aapl-0601"),
            builder.Run("AAPL", "2026-06-02", "opus", "2026-06-02 11:01:33", "aapl-0602"),
        ],
        "QCOM": [
            builder.Run("QCOM", "2026-06-01", "opus", "2026-06-02 00:08:03", "qcom-early"),
            builder.Run("QCOM", "2026-06-01", "opus", "2026-06-02 09:28:30", "qcom-late"),
            builder.Run("QCOM", "2026-06-01", "gpt-5.5", "2026-06-02 08:28:30", "qcom-gpt"),
        ],
    }

    selected = builder.latest_runs(runs, analysis_date="20260601")

    assert {(run.ticker, run.model): run.folder_name for run in selected} == {
        ("AAPL", "opus"): "aapl-0601",
        ("QCOM", "opus"): "qcom-late",
        ("QCOM", "gpt-5.5"): "qcom-gpt",
    }


@pytest.mark.unit
def test_build_daily_summaries_groups_dates_and_selects_latest_run(monkeypatch):
    builder = load_builder()
    runs = {
        "AAPL": [
            builder.Run("AAPL", "2026-06-01", "opus", "2026-06-01 20:12:03", "aapl-early"),
            builder.Run("AAPL", "2026-06-01", "opus", "2026-06-02 09:28:30", "aapl-late"),
            builder.Run("AAPL", "2026-06-01", "gpt-5.5", "2026-06-02 08:28:30", "aapl-gpt"),
            builder.Run("AAPL", "2026-06-02", "opus", "2026-06-02 11:01:33", "aapl-0602"),
        ],
        "MSFT": [
            builder.Run("MSFT", "2026-06-01", "opus", "2026-06-01 20:15:00", "msft-0601"),
        ],
    }
    selected_folders: list[str] = []

    def fake_summary_row(run):
        selected_folders.append(run.folder_name)
        return summary_row(builder, run.ticker, run.folder_name)

    monkeypatch.setattr(builder, "build_summary_row", fake_summary_row)

    summaries = builder.build_daily_summaries(runs)

    assert [summary.analysis_date for summary in summaries] == [
        "2026-06-02",
        "2026-06-01",
    ]
    assert selected_folders == ["aapl-0602", "aapl-gpt", "aapl-late", "msft-0601"]
    assert "aapl-early" not in selected_folders


@pytest.mark.unit
def test_daily_decision_summaries_render_newest_first_with_left_rail():
    builder = load_builder()
    summaries = [
        builder.DailySummary("2026-06-02", [summary_row(builder, "AAPL", "aapl-0602")]),
        builder.DailySummary("2026-06-01", [summary_row(builder, "MSFT", "msft-0601")]),
    ]

    text = "\n".join(builder.build_daily_decision_summaries(summaries, "20260602"))

    assert '<nav class="daily-summary-rail" aria-label="Analysis dates">' in text
    assert 'class="daily-summary-date daily-summary-date--active"' in text
    assert "#2026-06-02-decision-summary" in text
    assert "#2026-06-01-decision-summary" in text
    assert "| Ticker | Model | Suggestion |" in text
    assert "| [AAPL](./AAPL/aapl-0602/complete_report.md) | `opus` | Buy / Overweight |" in text
    assert text.index("## 2026-06-02 Decision Summary") < text.index(
        "## 2026-06-01 Decision Summary"
    )


@pytest.mark.unit
def test_decision_summary_rows_sort_by_ticker_alphabetically():
    builder = load_builder()
    rows = [
        summary_row(builder, "MSFT", "msft-0602", action="Buy"),
        summary_row(builder, "AAPL", "aapl-0602", action="Sell"),
        summary_row(builder, "GOOG", "goog-0602", action="Hold"),
    ]

    text = "\n".join(builder.build_decision_summary(rows, "20260602"))

    assert text.index("| [AAPL]") < text.index("| [GOOG]")
    assert text.index("| [GOOG]") < text.index("| [MSFT]")


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
def test_replace_decision_summary_replaces_daily_summary_block():
    builder = load_builder()
    home = (
        "# TradingAgents Reports\n"
        "\n"
        "## Daily Decision Summaries\n"
        "\n"
        "old daily block\n"
        "\n"
        "## 2026-06-01 Decision Summary\n"
        "\n"
        "old table\n"
        "\n"
        "## Regeneration Skill\n"
        "\n"
        "regen text\n"
    )

    out = builder.replace_decision_summary(
        home,
        ["## Daily Decision Summaries", "", "new daily block", ""],
    )

    assert "old daily block" not in out
    assert "old table" not in out
    assert "new daily block" in out
    assert "## Regeneration Skill\n\nregen text" in out


@pytest.mark.unit
def test_generated_pages_do_not_end_with_extra_blank_line():
    builder = load_builder()
    run = builder.Run("AAPL", "2026-06-02", "opus", "2026-06-02 10:10:10", "run")
    summaries = [builder.DailySummary("2026-06-02", [summary_row(builder, "AAPL", "run")])]

    home = builder.build_home({"AAPL": [run]}, 1, summaries, "20260602")
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
        "Last Close: $999.00\n",
        "**Current Price**: $123.45\n",
        "",
    ) == 123.45
    assert builder.extract_current_price(
        "Last Close: $999.00\n",
        "**Current Price**: n/a\n",
        "",
    ) is None
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


@pytest.mark.unit
def test_decision_parser_accepts_target_price_alias():
    builder = load_builder()

    assert builder.extract_price_target("**Target Price**: $212.50\n") == 212.5
    assert builder.extract_price_target("| **Fair Value** | **$198** |\n") == 198.0


@pytest.mark.unit
def test_summary_row_uses_current_price_when_target_missing(tmp_path, monkeypatch):
    builder = load_builder()
    docs = tmp_path / "docs"
    run_dir = docs / "AAPL" / "20260621_gpt-5-5_20260621_123508"
    (run_dir / "5_portfolio").mkdir(parents=True)
    (run_dir / "3_trading").mkdir()
    (run_dir / "5_portfolio" / "decision.md").write_text(
        "**Rating**: Hold\n\n"
        "**Current Price**: $298.01\n\n"
        "**Price Target**: n/a\n\n"
        "**Time Horizon**: 3-6 months\n",
        encoding="utf-8",
    )
    (run_dir / "3_trading" / "trader.md").write_text(
        "**Action**: Hold\n",
        encoding="utf-8",
    )
    (run_dir / "complete_report.md").write_text(
        "**Confidence:** Medium\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(builder, "DOCS_DIR", docs)

    row = builder.build_summary_row(
        builder.Run(
            "AAPL",
            "2026-06-21",
            "gpt-5-5",
            "2026-06-21 12:35:08",
            "20260621_gpt-5-5_20260621_123508",
        )
    )

    assert row.current_price == 298.01
    assert row.price_target == 298.01
    assert row.target_uplift == 0.0
    assert row.annualized_uplift == 0.0


@pytest.mark.unit
def test_main_removes_stale_generated_ticker_hubs(tmp_path, monkeypatch):
    builder = load_builder()
    docs = tmp_path / "docs"
    run_dir = docs / "AAPL" / "20260602_opus_20260602_101010"
    run_dir.mkdir(parents=True)
    (run_dir / "complete_report.md").write_text(
        "# Trading Analysis Report: AAPL\n\n"
        "### Portfolio Manager Decision\n"
        "**Rating**: Overweight\n"
        "**Action**: Buy\n"
        "**Current Price**: $10.00\n"
        "**Price Target**: $12.00\n"
        "**Confidence**: High\n"
        "**Time Horizon**: 6m\n",
        encoding="utf-8",
    )
    stale_dir = docs / "AMAT"
    stale_dir.mkdir()
    (stale_dir / "index.md").write_text("stale generated hub\n", encoding="utf-8")

    monkeypatch.setattr(builder, "DOCS_DIR", docs)

    assert builder.main(["--summary-analysis-date", "20260602"]) == 0
    assert not (stale_dir / "index.md").exists()
    assert not stale_dir.exists()
