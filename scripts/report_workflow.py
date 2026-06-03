"""Refresh local report docs and compile the MkDocs site.

This is the repo-local orchestration entrypoint for report refreshes. It
coordinates the existing report scripts rather than duplicating their parsing
and rendering logic:

    python scripts/report_workflow.py
    python scripts/report_workflow.py --analysis-date 20260602
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
MKDOCS_ROOT = ROOT
SITE_DIR: str | Path = "_site"

# Make repo-local modules importable when run as ``python scripts/...``.
sys.path.insert(0, str(ROOT))

from cli.report_headings import transform  # noqa: E402
from scripts import build_reports_site as site  # noqa: E402
from scripts import reassemble_complete_reports as reassembler  # noqa: E402


normalize_analysis_date = site.normalize_analysis_date

SUMMARY_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(\./([^/]+)/([^/]+)/complete_report\.md\)"
)
TRAILING_WHITESPACE_RE = re.compile(r"[ \t]+(?=\r?\n|$)")


class WorkflowError(Exception):
    """A user-actionable workflow failure."""


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def analysis_date_key(analysis_date: str) -> str:
    normalized = normalize_analysis_date(analysis_date)
    if normalized is None:
        raise WorkflowError("analysis date is required")
    return normalized.replace("-", "")


def discover_runs(docs_dir: Path = DOCS) -> dict[str, list[site.Run]]:
    runs_by_ticker: dict[str, list[site.Run]] = defaultdict(list)
    if not docs_dir.is_dir():
        raise WorkflowError(f"docs/ not found at {docs_dir}")

    for ticker_dir in sorted(docs_dir.iterdir()):
        if not ticker_dir.is_dir():
            continue
        if ticker_dir.name == "assets":
            continue
        if not site.TICKER_DIR_RE.match(ticker_dir.name):
            continue
        for run_dir in sorted(ticker_dir.iterdir()):
            run = site.parse_run_folder(ticker_dir, run_dir)
            if run is not None:
                runs_by_ticker[run.ticker].append(run)
    return dict(runs_by_ticker)


def latest_analysis_date(runs_by_ticker: dict[str, list[site.Run]]) -> str:
    dates = [run.analysis_date for runs in runs_by_ticker.values() for run in runs]
    if not dates:
        raise WorkflowError("No run folders found under docs/.")
    return max(dates)


def select_target_runs(
    runs_by_ticker: dict[str, list[site.Run]],
    analysis_date: str,
) -> dict[str, site.Run]:
    normalized = normalize_analysis_date(analysis_date)
    if normalized is None:
        raise WorkflowError("analysis date is required")

    selected: dict[str, site.Run] = {}
    for ticker, runs in runs_by_ticker.items():
        matching = [run for run in runs if run.analysis_date == normalized]
        if matching:
            selected[ticker] = sorted(
                matching,
                key=lambda run: (run.analysis_date, run.run_started),
                reverse=True,
            )[0]
    return selected


def require_full_coverage(
    runs_by_ticker: dict[str, list[site.Run]],
    selected: dict[str, site.Run],
    analysis_date: str,
) -> None:
    missing = sorted(ticker for ticker in runs_by_ticker if ticker not in selected)
    if missing:
        tickers = ", ".join(missing)
        raise WorkflowError(
            f"Analysis date {analysis_date} is incomplete; missing tickers: {tickers}"
        )


def report_path(run: site.Run) -> Path:
    return DOCS / run.ticker / run.folder_name / "complete_report.md"


def expected_stage_paths(run: site.Run) -> list[Path]:
    run_dir = DOCS / run.ticker / run.folder_name
    return [
        run_dir / rel_path
        for _, stages in reassembler.SECTIONS
        for rel_path, _ in stages
    ]


def ensure_complete_report(run: site.Run) -> bool:
    path = report_path(run)
    if path.is_file():
        return False

    run_dir = path.parent
    text = reassembler.reassemble(run_dir, run.ticker)
    if text is None:
        missing = [p for p in expected_stage_paths(run) if not p.is_file()]
        if not missing:
            missing = expected_stage_paths(run)
        missing_text = "\n".join(f"  - {display_path(p)}" for p in missing)
        raise WorkflowError(
            f"Cannot reassemble {display_path(path)}; missing stage files:\n"
            f"{missing_text}"
        )

    path.write_text(text, encoding="utf-8")
    return True


def normalize_report(run: site.Run) -> bool:
    path = report_path(run)
    text = path.read_text(encoding="utf-8", errors="replace")
    new_text = transform(text)
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def strip_front_matter(run: site.Run) -> bool:
    path = report_path(run)
    text = path.read_text(encoding="utf-8", errors="replace")
    new_text = site.FRONT_MATTER_RE.sub("", text, count=1)
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def strip_run_trailing_whitespace(run: site.Run) -> int:
    changed = 0
    run_dir = DOCS / run.ticker / run.folder_name
    for path in sorted(run_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        new_text = TRAILING_WHITESPACE_RE.sub("", text)
        if new_text == text:
            continue
        path.write_text(new_text, encoding="utf-8")
        changed += 1
    return changed


def process_selected_runs(selected: dict[str, site.Run]) -> None:
    reassembled = 0
    normalized = 0
    stripped = 0
    whitespace_stripped = 0
    for ticker in sorted(selected):
        run = selected[ticker]
        if ensure_complete_report(run):
            reassembled += 1
        if normalize_report(run):
            normalized += 1
        if strip_front_matter(run):
            stripped += 1
        whitespace_stripped += strip_run_trailing_whitespace(run)
    print(
        "Processed "
        f"{len(selected)} selected report(s): "
        f"{reassembled} reassembled, {normalized} normalized, "
        f"{stripped} front matter stripped, "
        f"{whitespace_stripped} markdown file(s) whitespace-stripped."
    )


def build_reports_site(analysis_date: str) -> None:
    old_docs_dir = site.DOCS_DIR
    site.DOCS_DIR = DOCS
    try:
        exit_code = site.main(["--summary-analysis-date", analysis_date_key(analysis_date)])
    finally:
        site.DOCS_DIR = old_docs_dir
    if exit_code != 0:
        raise WorkflowError("scripts/build_reports_site.py failed")


def decision_summary_rows(home_text: str, analysis_date: str) -> list[str]:
    heading = f"## {normalize_analysis_date(analysis_date)} Decision Summary"
    pattern = re.compile(
        rf"^{re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)",
        flags=re.M | re.S,
    )
    match = pattern.search(home_text)
    if match is None:
        raise WorkflowError(f"Could not find homepage summary heading: {heading}")

    rows = []
    for line in match.group("body").splitlines():
        if not line.startswith("|"):
            continue
        if line.startswith("| Ticker ") or line.startswith("| --- "):
            continue
        rows.append(line)
    return rows


def validate_homepage(
    analysis_date: str,
    selected: dict[str, site.Run],
) -> None:
    normalized = normalize_analysis_date(analysis_date)
    if normalized is None:
        raise WorkflowError("analysis date is required")
    key = analysis_date_key(normalized)
    index_path = DOCS / "index.md"
    home_text = index_path.read_text(encoding="utf-8", errors="replace")
    rows = decision_summary_rows(home_text, normalized)

    if len(rows) != len(selected):
        raise WorkflowError(
            f"Homepage summary has {len(rows)} row(s); expected {len(selected)}."
        )

    seen: set[str] = set()
    for row in rows:
        if "n/a" in row.lower():
            raise WorkflowError(f"Homepage summary row contains n/a: {row}")

        match = SUMMARY_LINK_RE.search(row)
        if match is None:
            raise WorkflowError(f"Homepage summary row has a bad report link: {row}")

        label, ticker, folder = match.groups()
        if label != ticker:
            raise WorkflowError(f"Homepage link label/ticker mismatch: {row}")
        if ticker not in selected:
            raise WorkflowError(f"Homepage summary has unexpected ticker: {ticker}")
        if ticker in seen:
            raise WorkflowError(f"Homepage summary has duplicate ticker: {ticker}")
        if not folder.startswith(f"{key}_"):
            raise WorkflowError(
                f"Homepage link for {ticker} must start with {key}_: {folder}"
            )
        if folder != selected[ticker].folder_name:
            expected = selected[ticker].folder_name
            raise WorkflowError(
                f"Homepage link for {ticker} points to {folder}; expected {expected}."
            )

        linked_report = DOCS / ticker / folder / "complete_report.md"
        if not linked_report.is_file():
            raise WorkflowError(f"Homepage report link is missing: {linked_report}")
        seen.add(ticker)

    missing = sorted(set(selected) - seen)
    if missing:
        raise WorkflowError(
            "Homepage summary is missing selected tickers: " + ", ".join(missing)
        )


def mkdocs_command(site_dir: str | Path = "_site") -> list[str]:
    local_mkdocs = ROOT / ".venv" / "bin" / "mkdocs"
    executable = str(local_mkdocs) if local_mkdocs.is_file() else "mkdocs"
    return [executable, "build", "--strict", "--site-dir", str(site_dir)]


def run_mkdocs_build() -> None:
    result = subprocess.run(mkdocs_command(SITE_DIR), cwd=MKDOCS_ROOT)
    if result.returncode != 0:
        raise WorkflowError("mkdocs build --strict --site-dir _site failed")


def run_workflow(analysis_date: str | None = None) -> None:
    runs_by_ticker = discover_runs(DOCS)
    target_date = normalize_analysis_date(analysis_date) if analysis_date else latest_analysis_date(runs_by_ticker)
    if target_date is None:
        raise WorkflowError("analysis date is required")

    selected = select_target_runs(runs_by_ticker, target_date)
    require_full_coverage(runs_by_ticker, selected, target_date)
    process_selected_runs(selected)
    build_reports_site(target_date)
    validate_homepage(target_date, selected)
    run_mkdocs_build()
    print(
        f"Refreshed {len(selected)} report(s) for {target_date}; "
        "compiled _site/index.html."
    )


def run_dry_run(analysis_date: str | None = None) -> None:
    global DOCS, MKDOCS_ROOT, SITE_DIR

    with tempfile.TemporaryDirectory(prefix="report-workflow-") as tmp:
        tmp_root = Path(tmp)
        tmp_docs = tmp_root / "docs"
        shutil.copytree(DOCS, tmp_docs)
        shutil.copy2(ROOT / "mkdocs.yml", tmp_root / "mkdocs.yml")

        old_docs = DOCS
        old_mkdocs_root = MKDOCS_ROOT
        old_site_dir = SITE_DIR
        DOCS = tmp_docs
        MKDOCS_ROOT = tmp_root
        SITE_DIR = "_site"
        try:
            run_workflow(analysis_date)
        finally:
            DOCS = old_docs
            MKDOCS_ROOT = old_mkdocs_root
            SITE_DIR = old_site_dir

    print("Dry run complete; no repo files were changed by the workflow.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--analysis-date",
        help="Target analysis date, using YYYYMMDD or YYYY-MM-DD. Defaults to latest.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run against a temporary copy of docs/ and compile a temporary _site.",
    )
    args = parser.parse_args(argv)
    try:
        args.analysis_date = normalize_analysis_date(args.analysis_date)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.dry_run:
            run_dry_run(args.analysis_date)
        else:
            run_workflow(args.analysis_date)
    except WorkflowError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
