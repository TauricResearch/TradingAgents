"""Reassemble missing ``complete_report.md`` files from per-stage outputs.

When a run is interrupted after its agent stages are written to disk but
before the consolidated report is assembled, the run folder ends up with
``1_analysts/``, ``2_research/`` ... ``5_portfolio/`` populated but no
``complete_report.md``. ``scripts/build_reports_site.py`` then links the
ticker's latest run to a file that doesn't exist, breaking
``mkdocs build --strict``.

This script rebuilds ``complete_report.md`` from the stage files, mirroring
the section layout and heading normalization of ``save_report_to_disk`` in
``cli/main.py`` so reassembled reports are byte-compatible with freshly
generated ones.

Run locally:

    python scripts/reassemble_complete_reports.py

Idempotent and non-destructive: only writes ``complete_report.md`` for run
folders that are missing it but have at least one stage file. Existing
reports are never overwritten.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

# Make the repo root importable when run as ``python scripts/...``.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.report_headings import transform  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# Folder name tail records the run start: <DATE>_<MODEL>_<RUN_DATE>_<RUN_TIME>.
RUN_TS_RE = re.compile(r"_(?P<d>\d{8})_(?P<t>\d{6})$")

# (section heading, [(stage file relative path, agent H3 label), ...]).
# Order and labels match ``save_report_to_disk`` in cli/main.py.
SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "## I. Analyst Team Reports",
        [
            ("1_analysts/market.md", "Market Analyst"),
            ("1_analysts/sentiment.md", "Sentiment Analyst"),
            ("1_analysts/news.md", "News Analyst"),
            ("1_analysts/fundamentals.md", "Fundamentals Analyst"),
        ],
    ),
    (
        "## II. Research Team Decision",
        [
            ("2_research/bull.md", "Bull Researcher"),
            ("2_research/bear.md", "Bear Researcher"),
            ("2_research/manager.md", "Research Manager"),
        ],
    ),
    (
        "## III. Trading Team Plan",
        [("3_trading/trader.md", "Trader")],
    ),
    (
        "## IV. Risk Management Team Decision",
        [
            ("4_risk/aggressive.md", "Aggressive Analyst"),
            ("4_risk/conservative.md", "Conservative Analyst"),
            ("4_risk/neutral.md", "Neutral Analyst"),
        ],
    ),
    (
        "## V. Portfolio Manager Decision",
        [("5_portfolio/decision.md", "Portfolio Manager")],
    ),
]


def generated_timestamp(run_dir: Path) -> str:
    """Prefer the run-start timestamp in the folder name; fall back to mtime."""
    m = RUN_TS_RE.search(run_dir.name)
    if m:
        d, t = m.group("d"), m.group("t")
        return f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}:{t[4:6]}"
    return datetime.fromtimestamp(run_dir.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def reassemble(run_dir: Path, ticker: str) -> str | None:
    """Build ``complete_report.md`` text from stage files, or None if empty."""
    sections: list[str] = []
    for heading, stages in SECTIONS:
        parts = []
        for rel_path, label in stages:
            path = run_dir / rel_path
            if path.is_file():
                body = path.read_text(encoding="utf-8", errors="replace").strip()
                if body:
                    parts.append(f"### {label}\n{body}")
        if parts:
            sections.append(f"{heading}\n\n" + "\n\n".join(parts))

    if not sections:
        return None

    header = (
        f"# Trading Analysis Report: {ticker}\n\n"
        f"Generated: {generated_timestamp(run_dir)}\n\n"
    )
    return transform(header + "\n\n".join(sections)) + "\n"


def main() -> int:
    if not DOCS.is_dir():
        print(f"docs/ not found at {DOCS}", file=sys.stderr)
        return 1

    written = 0
    candidates = 0
    for ticker_dir in sorted(DOCS.iterdir()):
        if not ticker_dir.is_dir():
            continue
        for run_dir in sorted(ticker_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            report = run_dir / "complete_report.md"
            if report.is_file():
                continue
            candidates += 1
            text = reassemble(run_dir, ticker_dir.name.upper())
            if text is None:
                print(f"  skip (no stage files): {run_dir.relative_to(ROOT)}")
                continue
            report.write_text(text, encoding="utf-8")
            written += 1
            print(f"  wrote: {report.relative_to(ROOT)}")

    print(f"Reassembled {written} of {candidates} run folder(s) missing complete_report.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
