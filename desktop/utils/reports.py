"""Shared report file discovery and display constants.

Extracted from detail.py and compare.py to eliminate the 70-line
duplication of ``_FILE_TITLES``, ``_PHASE_TITLES``, and the
``discover_report_files()`` function.
"""

from __future__ import annotations

from pathlib import Path

# ── Markdown rendering extras (shared by report_section.py, detail.py, compare.py)

MD_EXTRAS: list[str] = [
    "tables",
    "fenced-code-blocks",
    "strike",
    "task_list",
    "cuddled-lists",
    "header-ids",
]

# ── Phase directory titles (numbered subdirs)

PHASE_TITLES: dict[str, str] = {
    "1_analysts": "Analysts",
    "2_research": "Research Team",
    "3_trading": "Trading Team",
    "4_risk": "Risk Management",
    "5_portfolio": "Portfolio Management",
}

# ── Individual file display titles

FILE_TITLES: dict[str, str] = {
    # New format (short names in subdirs)
    "fundamentals": "Fundamentals Analysis",
    "market": "Market Analysis",
    "news": "News Analysis",
    "sentiment": "Social Sentiment",
    "bull": "Bull Researcher",
    "bear": "Bear Researcher",
    "manager": "Research Manager Decision",
    "trader": "Trading Team Plan",
    "aggressive": "Aggressive Risk Analyst",
    "neutral": "Neutral Risk Analyst",
    "conservative": "Conservative Risk Analyst",
    "decision": "Portfolio Management Decision",
    # Old format (flat reports/ directory)
    "market_report": "Market Analysis",
    "sentiment_report": "Social Sentiment",
    "news_report": "News Analysis",
    "fundamentals_report": "Fundamentals Analysis",
    "investment_plan": "Research Team Decision",
    "trader_investment_plan": "Trading Team Plan",
    "final_trade_decision": "Portfolio Management Decision",
}

# ── Log entry type → Quasar color mapping

TYPE_COLORS: dict[str, str] = {
    "System": "blue-4",
    "Agent": "green-4",
    "User": "yellow-4",
    "Data": "purple-4",
    "Tool": "orange-4",
    "Control": "grey-5",
    "Error": "red-4",
}

# ── Status badge color mapping

STATUS_COLORS: dict[str, str] = {
    "completed": "green",
    "running": "blue",
    "failed": "red",
    "interrupted": "orange",
}


def discover_report_files(root: Path) -> list[tuple[str, Path]]:
    """Find all report markdown files in either directory layout.

    Returns a list of ``(display_title, path)`` tuples in a logical
    order (analysts -> research -> trading -> risk -> portfolio).

    Supports three layouts:
    - Numbered subdirectories (``1_analysts/``, ``2_research/``, ...)
    - Flat ``reports/`` subdirectory
    - Markdown files directly in root
    """
    sections: list[tuple[str, Path]] = []

    # New format: numbered subdirectories
    phase_dirs = sorted(
        (d for d in root.iterdir() if d.is_dir() and d.name[0].isdigit()),
        key=lambda d: d.name,
    )
    if phase_dirs:
        for phase_dir in phase_dirs:
            phase_label = PHASE_TITLES.get(phase_dir.name, phase_dir.name)
            for md in sorted(phase_dir.glob("*.md")):
                title = FILE_TITLES.get(
                    md.stem,
                    f"{phase_label} — {md.stem.replace('_', ' ').title()}",
                )
                sections.append((f"{phase_label} / {title}", md))
        return sections

    # Old format: flat reports/ subdirectory
    reports_dir = root / "reports"
    if reports_dir.is_dir():
        for md in sorted(reports_dir.glob("*.md")):
            title = FILE_TITLES.get(md.stem, md.stem.replace("_", " ").title())
            sections.append((title, md))
        return sections

    # Fallback: any .md files directly in root (excluding complete_report)
    for md in sorted(root.glob("*.md")):
        if md.name == "complete_report.md":
            continue
        title = FILE_TITLES.get(md.stem, md.stem.replace("_", " ").title())
        sections.append((title, md))

    return sections


def status_chip(status: str) -> None:
    """Render a small colored status chip (shared by detail.py & compare.py)."""
    from nicegui import ui

    color = STATUS_COLORS.get(status, "grey")
    ui.label(status.capitalize()).classes(
        f"text-caption text-white bg-{color} q-px-sm q-py-xs rounded-borders"
    )
