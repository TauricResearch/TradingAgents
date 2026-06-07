"""Local India filing readers."""

from __future__ import annotations

import csv
from pathlib import Path

from tradingagents.dataflows.india.quality import unavailable_response
from tradingagents.dataflows.india.symbols import safe_india_ticker_component


FILING_ROOT = Path("data/india/filings")
TEXT_GLOBS = (
    "concall/*.txt",
    "results/*.csv",
    "notes/*.md",
)
PDF_GLOBS = (
    "annual_report/*.pdf",
    "investor_presentations/*.pdf",
)


def _read_csv(path: Path) -> str:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return ""
    return "\n".join("| " + " | ".join(row) + " |" for row in rows[:40])


def get_local_filing_notes(symbol: str, root: Path = FILING_ROOT) -> str:
    safe_symbol = safe_india_ticker_component(symbol)
    base = root / safe_symbol
    if not base.exists():
        return unavailable_response(
            "local_filings",
            safe_symbol,
            f"No local filings found under {base}. Add user-supplied files before relying on this source.",
        )

    sections: list[str] = [f"# Local Filing Notes: {safe_symbol}"]
    for pattern in TEXT_GLOBS:
        for path in sorted(base.glob(pattern)):
            if path.suffix.lower() == ".csv":
                body = _read_csv(path)
            else:
                body = path.read_text(encoding="utf-8", errors="replace")
            sections.append(f"## {path.relative_to(base)}\n\n{body[:12000]}")

    pdf_paths = [path for pattern in PDF_GLOBS for path in sorted(base.glob(pattern))]
    if pdf_paths:
        names = "\n".join(f"- {path.relative_to(base)}" for path in pdf_paths)
        sections.append(
            "## PDF Filings\n\n"
            "PDF files are present but OCR/heavy extraction is intentionally not enabled by default. "
            "Convert key pages to text and place them under `concall/`, `notes/`, or `results/`.\n\n"
            f"{names}"
        )

    if len(sections) == 1:
        return unavailable_response("local_filings", safe_symbol, "No supported text, CSV, or markdown filing notes were found.")
    return "\n\n".join(sections)
