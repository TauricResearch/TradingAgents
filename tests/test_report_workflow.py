from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def load_workflow():
    path = Path(__file__).resolve().parents[1] / "scripts" / "report_workflow.py"
    spec = importlib.util.spec_from_file_location("report_workflow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_run(
    docs_dir: Path,
    ticker: str,
    folder: str,
    *,
    complete: bool = True,
    stage_files: dict[str, str] | None = None,
) -> Path:
    run_dir = docs_dir / ticker / folder
    run_dir.mkdir(parents=True)
    if complete:
        (run_dir / "complete_report.md").write_text(
            f"# Trading Analysis Report: {ticker}\n",
            encoding="utf-8",
        )
    for rel_path, body in (stage_files or {}).items():
        path = run_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return run_dir


@pytest.mark.unit
def test_latest_date_detection_chooses_max_folder_prefix(tmp_path):
    workflow = load_workflow()
    docs = tmp_path / "docs"
    make_run(docs, "AAPL", "20260601_opus_20260601_010101")
    make_run(docs, "AAPL", "20260602_opus_20260602_010101")
    make_run(docs, "MSFT", "20260601_opus_20260601_010101")

    runs = workflow.discover_runs(docs)

    assert workflow.latest_analysis_date(runs) == "2026-06-02"


@pytest.mark.unit
@pytest.mark.parametrize("value", ["20260602", "2026-06-02"])
def test_explicit_analysis_date_accepts_compact_and_iso(value):
    workflow = load_workflow()

    assert workflow.normalize_analysis_date(value) == "2026-06-02"
    assert workflow.analysis_date_key(workflow.normalize_analysis_date(value)) == "20260602"


@pytest.mark.unit
def test_incomplete_target_date_coverage_fails_with_missing_tickers(tmp_path):
    workflow = load_workflow()
    docs = tmp_path / "docs"
    make_run(docs, "AAPL", "20260602_opus_20260602_010101")
    make_run(docs, "MSFT", "20260601_opus_20260601_010101")
    runs = workflow.discover_runs(docs)
    selected = workflow.select_target_runs(runs, "2026-06-02")

    with pytest.raises(workflow.WorkflowError, match="MSFT"):
        workflow.require_full_coverage(runs, selected, "2026-06-02")


@pytest.mark.unit
def test_missing_complete_report_is_reassembled_from_stage_files(tmp_path, monkeypatch):
    workflow = load_workflow()
    docs = tmp_path / "docs"
    run_dir = make_run(
        docs,
        "AAPL",
        "20260602_opus_20260602_101010",
        complete=False,
        stage_files={"1_analysts/market.md": "# Market body\n"},
    )
    run = workflow.site.parse_run_folder(run_dir.parent, run_dir)
    assert run is not None
    monkeypatch.setattr(workflow, "DOCS", docs)

    workflow.ensure_complete_report(run)

    report = run_dir / "complete_report.md"
    text = report.read_text(encoding="utf-8")
    assert "# Trading Analysis Report: AAPL" in text
    assert "### Market Analyst" in text
    assert "#### Market body" in text


@pytest.mark.unit
def test_missing_complete_report_without_stage_files_fails_with_paths(tmp_path, monkeypatch):
    workflow = load_workflow()
    docs = tmp_path / "docs"
    run_dir = make_run(
        docs,
        "AAPL",
        "20260602_opus_20260602_101010",
        complete=False,
    )
    run = workflow.site.parse_run_folder(run_dir.parent, run_dir)
    assert run is not None
    monkeypatch.setattr(workflow, "DOCS", docs)

    with pytest.raises(workflow.WorkflowError, match="1_analysts/market.md"):
        workflow.ensure_complete_report(run)


@pytest.mark.unit
def test_strip_run_trailing_whitespace_cleans_report_and_stage_files(tmp_path, monkeypatch):
    workflow = load_workflow()
    docs = tmp_path / "docs"
    run_dir = make_run(
        docs,
        "AAPL",
        "20260602_opus_20260602_101010",
        stage_files={"1_analysts/market.md": "stage line  \nkeep\n"},
    )
    (run_dir / "complete_report.md").write_text("report line\t\n", encoding="utf-8")
    run = workflow.site.parse_run_folder(run_dir.parent, run_dir)
    assert run is not None
    monkeypatch.setattr(workflow, "DOCS", docs)

    assert workflow.strip_run_trailing_whitespace(run) == 2
    assert (run_dir / "complete_report.md").read_text(encoding="utf-8") == "report line\n"
    assert (run_dir / "1_analysts" / "market.md").read_text(encoding="utf-8") == "stage line\nkeep\n"


@pytest.mark.unit
def test_homepage_validation_accepts_selected_date_links(tmp_path, monkeypatch):
    workflow = load_workflow()
    docs = tmp_path / "docs"
    run_dir = make_run(docs, "AAPL", "20260602_opus_20260602_101010")
    run = workflow.site.parse_run_folder(run_dir.parent, run_dir)
    assert run is not None
    monkeypatch.setattr(workflow, "DOCS", docs)
    (docs / "index.md").write_text(
        (
            "# TradingAgents Reports\n\n"
            "## 2026-06-02 Decision Summary\n\n"
            "| Ticker | Suggestion | Current | Target | Target uplift | 1Y uplift | Confidence | Horizon |\n"
            "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |\n"
            "| [AAPL](./AAPL/20260602_opus_20260602_101010/complete_report.md) | Buy / Overweight | $10.00 | $12.00 | +20.0% | +40.0% | High | 6m |\n\n"
            "## Regeneration Skill\n"
        ),
        encoding="utf-8",
    )

    workflow.validate_homepage("2026-06-02", {"AAPL": run})


@pytest.mark.unit
@pytest.mark.parametrize(
    ("row", "create_report", "error_match"),
    [
        (
            "| [AAPL](./AAPL/20260602_opus_20260602_101010/complete_report.md) | Buy / Overweight | n/a | $12.00 | +20.0% | +40.0% | High | 6m |",
            True,
            "n/a",
        ),
        (
            "| [AAPL](./AAPL/20260602_opus_20260602_101010/not_report.md) | Buy / Overweight | $10.00 | $12.00 | +20.0% | +40.0% | High | 6m |",
            True,
            "report link",
        ),
        (
            "| [AAPL](./AAPL/20260602_opus_20260602_101010/complete_report.md) | Buy / Overweight | $10.00 | $12.00 | +20.0% | +40.0% | High | 6m |",
            False,
            "missing",
        ),
        (
            "| [AAPL](./AAPL/20260601_opus_20260601_101010/complete_report.md) | Buy / Overweight | $10.00 | $12.00 | +20.0% | +40.0% | High | 6m |",
            True,
            "20260602_",
        ),
    ],
)
def test_homepage_validation_rejects_bad_rows(
    tmp_path,
    monkeypatch,
    row,
    create_report,
    error_match,
):
    workflow = load_workflow()
    docs = tmp_path / "docs"
    run_dir = make_run(
        docs,
        "AAPL",
        "20260602_opus_20260602_101010",
        complete=create_report,
    )
    make_run(docs, "AAPL", "20260601_opus_20260601_101010")
    run = workflow.site.parse_run_folder(run_dir.parent, run_dir)
    assert run is not None
    monkeypatch.setattr(workflow, "DOCS", docs)
    (docs / "index.md").write_text(
        (
            "# TradingAgents Reports\n\n"
            "## 2026-06-02 Decision Summary\n\n"
            "| Ticker | Suggestion | Current | Target | Target uplift | 1Y uplift | Confidence | Horizon |\n"
            "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |\n"
            f"{row}\n\n"
            "## Regeneration Skill\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(workflow.WorkflowError, match=error_match):
        workflow.validate_homepage("2026-06-02", {"AAPL": run})


@pytest.mark.unit
def test_workflow_command_order_is_process_build_validate_mkdocs(monkeypatch):
    workflow = load_workflow()
    run = workflow.site.Run(
        "AAPL",
        "2026-06-02",
        "opus",
        "2026-06-02 10:10:10",
        "20260602_opus_20260602_101010",
    )
    calls: list[str] = []
    monkeypatch.setattr(workflow, "discover_runs", lambda docs_dir: {"AAPL": [run]})
    monkeypatch.setattr(workflow, "select_target_runs", lambda runs, date: {"AAPL": run})
    monkeypatch.setattr(workflow, "require_full_coverage", lambda runs, selected, date: None)
    monkeypatch.setattr(workflow, "process_selected_runs", lambda selected: calls.append("process"))
    monkeypatch.setattr(workflow, "build_reports_site", lambda date: calls.append("build_reports_site"))
    monkeypatch.setattr(workflow, "validate_homepage", lambda date, selected: calls.append("validate_homepage"))
    monkeypatch.setattr(workflow, "run_mkdocs_build", lambda: calls.append("mkdocs"))

    workflow.run_workflow(analysis_date="20260602")

    assert calls == ["process", "build_reports_site", "validate_homepage", "mkdocs"]


@pytest.mark.unit
def test_dry_run_uses_copied_docs_and_restores_repo_paths(tmp_path, monkeypatch):
    workflow = load_workflow()
    docs = tmp_path / "docs"
    make_run(docs, "AAPL", "20260602_opus_20260602_101010")
    original_mkdocs_root = workflow.MKDOCS_ROOT
    original_site_dir = workflow.SITE_DIR
    observed: dict[str, Path | str] = {}
    monkeypatch.setattr(workflow, "DOCS", docs)

    def fake_run_workflow(analysis_date):
        observed["analysis_date"] = analysis_date
        observed["docs"] = workflow.DOCS
        observed["mkdocs_root"] = workflow.MKDOCS_ROOT
        observed["site_dir"] = Path(workflow.SITE_DIR)
        assert workflow.DOCS != docs
        assert (workflow.DOCS / "AAPL" / "20260602_opus_20260602_101010").is_dir()
        (workflow.DOCS / "dry-run-marker").write_text("temp only", encoding="utf-8")

    monkeypatch.setattr(workflow, "run_workflow", fake_run_workflow)

    workflow.run_dry_run("20260602")

    assert observed["analysis_date"] == "20260602"
    assert observed["mkdocs_root"] != workflow.ROOT
    assert observed["site_dir"] == Path("_site")
    assert not (docs / "dry-run-marker").exists()
    assert workflow.DOCS == docs
    assert workflow.MKDOCS_ROOT == original_mkdocs_root
    assert workflow.SITE_DIR == original_site_dir
