"""Daily digest consolidation.

Appends individual report entries (analyze or scan) into a single
``daily_digest.md`` file under ``reports/daily/{date}/``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tradingagents.report_paths import get_digest_path


def append_to_digest(date: str, entry_type: str, label: str, content: str) -> Path:
    """Append a timestamped section to the daily digest file.

    Parameters
    ----------
    date:
        Date string (YYYY-MM-DD) used to locate the digest file.
    entry_type:
        Category of the entry, e.g. ``"analyze"`` or ``"scan"``.
    label:
        Human-readable label, e.g. ticker symbol or ``"Market Scan"``.
    content:
        The report content to append.

    Returns
    -------
    Path
        The path to the digest file.
    """
    digest_path = get_digest_path(date)
    digest_path.parent.mkdir(parents=True, exist_ok=True)

    existing = digest_path.read_text() if digest_path.exists() else ""

    if not existing:
        existing = f"# Daily Trading Report — {date}\n\n"

    timestamp = datetime.now().strftime("%H:%M")
    section = f"---\n### {timestamp} — {label} ({entry_type})\n\n{content}\n\n"

    digest_path.write_text(existing + section)
    return digest_path
