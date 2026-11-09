"""The reports already on disk, for the web console's archive.

The page's History tab lists the runs this process remembers, so restarting the
server empties it. The reports themselves outlive that: a run writes them under
the results directory in one of two shapes.

A finished run writes ``reports/<TICKER>_<stamp>/`` — the tree
``TradingAgentsGraph.save_reports`` produces, with one markdown file per agent,
a consolidated ``complete_report.md`` and, unless disabled, a self-contained
``complete_report.html``. Its header records the ticker, the analysis date and
the rating.

A run also fills ``<TICKER>/<analysis date>/reports/`` as each agent finishes,
so a run that was cancelled or failed still leaves what it had. That folder
carries no header and no consolidated report.

The archive lists the finished reports. A run folder is listed only when no
finished report covers the same ticker and analysis date, so a completed run is
not listed twice while an unfinished one still has something to read.

Entries are addressed by their path relative to the results directory. Nothing
is taken on trust: a path from a request is resolved and must stay inside the
results directory, and must also be one this module scanned, so a crafted value
cannot read an arbitrary file.
"""

from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from tradingagents.agents.rating import RATINGS_5_TIER, extract_rating

# The header lines `tradingagents.reporting._header` writes. Read from the top
# of the file only: a report runs to thousands of lines.
_TITLE_RE = re.compile(r"^#\s+Trading Analysis Report:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_DATE_RE = re.compile(r"^-\s+Analysis date:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_RATING_RE = re.compile(r"^-\s+Rating:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_HEADER_BYTES = 2048

_RATING_BY_LOWER = {rating.lower(): rating for rating in RATINGS_5_TIER}

# The agent files inside a finished report tree, in reading order.
_FINISHED_SECTIONS: tuple[tuple[str, str], ...] = (
    ("1_analysts/market.md", "Market Analyst"),
    ("1_analysts/sentiment.md", "Sentiment Analyst"),
    ("1_analysts/news.md", "News Analyst"),
    ("1_analysts/fundamentals.md", "Fundamentals Analyst"),
    ("2_research/bull.md", "Bull Researcher"),
    ("2_research/bear.md", "Bear Researcher"),
    ("2_research/manager.md", "Research Manager"),
    ("3_trading/trader.md", "Trader"),
    ("4_risk/aggressive.md", "Aggressive Analyst"),
    ("4_risk/conservative.md", "Conservative Analyst"),
    ("4_risk/neutral.md", "Neutral Analyst"),
    ("5_portfolio/decision.md", "Portfolio Manager"),
)

# The files a run writes into its own ``reports`` folder, keyed by the state
# field each one holds.
_RUN_SECTIONS: tuple[tuple[str, str], ...] = (
    ("market_report.md", "Market Analyst"),
    ("sentiment_report.md", "Sentiment Analyst"),
    ("news_report.md", "News Analyst"),
    ("fundamentals_report.md", "Fundamentals Analyst"),
    ("investment_plan.md", "Research Manager"),
    ("trader_investment_plan.md", "Trader"),
    ("final_trade_decision.md", "Portfolio Manager"),
)


class ArchivePathError(ValueError):
    """A path that does not name an archived report; the API turns it into a 404."""


@dataclass
class ArchivedReport:
    """One report on disk, as much as the list needs to show it."""

    id: str                      # path relative to the results directory
    ticker: str
    analysis_date: str | None
    rating: str | None
    source: str                  # "report" for a finished tree, "run" for a run folder
    created_at: float
    has_html: bool = False
    has_markdown: bool = True
    section_titles: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "analysis_date": self.analysis_date,
            "rating": self.rating,
            "source": self.source,
            "created_at": self.created_at,
            "has_html": self.has_html,
            "has_markdown": self.has_markdown,
            "section_titles": list(self.section_titles),
        }


def _header(path: Path) -> tuple[str | None, str | None, str | None]:
    """The ticker, analysis date and rating from a report's header, when it has one."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            head = handle.read(_HEADER_BYTES)
    except OSError:
        return None, None, None
    title = _TITLE_RE.search(head)
    date = _DATE_RE.search(head)
    rating = _RATING_RE.search(head)
    return (
        title.group(1) if title else None,
        date.group(1) if date else None,
        rating.group(1) if rating else None,
    )


# The header lines that record how the run was made, parsed for "re-run with
# these settings". Only what the page's form offers is read; anything else in
# the header is display text, not configuration.
_SETTINGS_RE = re.compile(r"^-\s+TradingAgents\s+\S+:\s*(.+)$", re.MULTILINE)
_ANALYSTS_RE = re.compile(r"^-\s+Analysts:\s*(.+)$", re.MULTILINE)
_ROUNDS_RE = re.compile(r"research debate rounds\s+(\d+)", re.IGNORECASE)
_RISK_ROUNDS_RE = re.compile(r"risk debate rounds\s+(\d+)", re.IGNORECASE)


def rerun_settings(results_dir: Path, entry_id: str) -> dict:
    """The form answers a report's header records, for pre-filling a re-run.

    The header names the models and the analyst selection as text, not as
    fields, so what comes back is a best effort: the ticker, date and analysts
    are exact, the models are read from the header's model line and offered as
    custom IDs the page can show and change.
    """
    entry = get_report(results_dir, entry_id)
    directory = _entry_directory(results_dir, entry)
    markdown = directory / "complete_report.md"
    try:
        head = markdown.read_text(encoding="utf-8", errors="replace")[:_HEADER_BYTES]
    except OSError:
        head = ""

    settings: dict = {
        "ticker": entry.ticker,
        "analysis_date": entry.analysis_date,
        "analysts": [],
        "quick_think_llm": None,
        "deep_think_llm": None,
        "research_depth": None,
    }
    analysts = _ANALYSTS_RE.search(head)
    if analysts:
        names = []
        for name in analysts.group(1).split(";")[0].split(","):
            name = name.strip().lower()
            if name == "sentiment":
                names.append("social")
            elif name in {"market", "social", "news", "fundamentals"}:
                names.append(name)
        settings["analysts"] = names
    rounds = _ROUNDS_RE.search(head)
    if rounds:
        settings["research_depth"] = int(rounds.group(1))
    models = _SETTINGS_RE.search(head)
    if models:
        text = models.group(1)
        # One provider for both tiers: "openai, deep gpt-6-sol, quick gpt-6-luna".
        # A tier on its own provider: "deep openai gpt-6-sol, quick anthropic claude-5".
        single = re.search(r"^\s*([^\s,]+),\s*deep\s+([^\s,]+),\s*quick\s+([^\s,]+)", text)
        split = re.search(r"\bdeep\s+(\S+)\s+([^\s,]+),\s*quick\s+(\S+)\s+([^\s,]+)", text)
        if single:
            settings["deep_think_llm"] = single.group(2)
            settings["quick_think_llm"] = single.group(3)
        elif split:
            settings["deep_think_llm"] = split.group(2)
            settings["quick_think_llm"] = split.group(4)
    return settings


def _canonical_rating(value: str | None) -> str | None:
    """The 5-tier rating a header line names, or None for REVIEW and anything unknown."""
    if not value:
        return None
    return _RATING_BY_LOWER.get(value.strip().strip("*_ ").lower())


def _sections_in(directory: Path, layout: tuple[tuple[str, str], ...]) -> list[tuple[Path, str]]:
    found = []
    for relative, title in layout:
        path = directory / relative
        if path.is_file():
            found.append((path, title))
    return found


def _finished_reports(results_dir: Path) -> list[ArchivedReport]:
    reports_root = results_dir / "reports"
    if not reports_root.is_dir():
        return []
    entries = []
    for directory in sorted(reports_root.iterdir()):
        if not directory.is_dir():
            continue
        markdown = directory / "complete_report.md"
        if not markdown.is_file():
            continue
        ticker, analysis_date, rating = _header(markdown)
        sections = _sections_in(directory, _FINISHED_SECTIONS)
        entries.append(ArchivedReport(
            id=directory.relative_to(results_dir).as_posix(),
            # A tree whose header could not be read still lists under its folder
            # name, so a damaged report stays visible instead of disappearing.
            ticker=ticker or directory.name.split("_")[0],
            analysis_date=analysis_date,
            rating=_canonical_rating(rating),
            source="report",
            created_at=markdown.stat().st_mtime,
            has_html=(directory / "complete_report.html").is_file(),
            section_titles=[title for _path, title in sections],
        ))
    return entries


def _covered(entries: list[ArchivedReport]) -> set[tuple[str, str]]:
    """The (ticker, analysis date) pairs a finished report already accounts for."""
    return {
        (entry.ticker, entry.analysis_date)
        for entry in entries
        if entry.analysis_date
    }


def _run_folders(results_dir: Path, covered: set[tuple[str, str]]) -> list[ArchivedReport]:
    if not results_dir.is_dir():
        return []
    entries = []
    for ticker_dir in sorted(results_dir.iterdir()):
        if not ticker_dir.is_dir() or ticker_dir.name == "reports":
            continue
        for date_dir in sorted(ticker_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            sections_dir = date_dir / "reports"
            if not sections_dir.is_dir():
                continue
            sections = _sections_in(sections_dir, _RUN_SECTIONS)
            if not sections:
                continue
            if (ticker_dir.name, date_dir.name) in covered:
                continue
            decision = sections_dir / "final_trade_decision.md"
            rating = None
            if decision.is_file():
                # A run's decided file carries no header; its rating is the
                # decision's own "Rating: X" line, so read it with the parser
                # every other caller uses.
                try:
                    rating = extract_rating(decision.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    rating = None
            newest = max(path.stat().st_mtime for path, _title in sections)
            entries.append(ArchivedReport(
                id=date_dir.relative_to(results_dir).as_posix(),
                ticker=ticker_dir.name,
                analysis_date=date_dir.name,
                rating=rating,
                source="run",
                created_at=newest,
                has_html=False,
                section_titles=[title for _path, title in sections],
            ))
    return entries


def list_reports(results_dir: Path) -> list[ArchivedReport]:
    """Every archived report, newest first."""
    results_dir = Path(results_dir)
    finished = _finished_reports(results_dir)
    entries = finished + _run_folders(results_dir, _covered(finished))
    return sorted(entries, key=lambda entry: entry.created_at, reverse=True)


def _resolve(results_dir: Path, entry_id: str) -> ArchivedReport:
    """The entry a request names, checked against what was actually scanned."""
    for entry in list_reports(results_dir):
        if entry.id == entry_id:
            return entry
    raise ArchivePathError(f"no archived report named {entry_id!r}")


def get_report(results_dir: Path, entry_id: str) -> ArchivedReport:
    """One entry by id, refusing anything that is not an archived report."""
    return _resolve(Path(results_dir), entry_id)


def _entry_directory(results_dir: Path, entry: ArchivedReport) -> Path:
    """The entry's folder, confirmed to sit inside the results directory."""
    root = Path(results_dir).resolve()
    directory = (root / entry.id).resolve()
    if directory != root and root not in directory.parents:
        raise ArchivePathError(f"{entry.id!r} resolves outside the results directory")
    return directory


def read_sections(results_dir: Path, entry_id: str) -> list[dict]:
    """The entry's agent reports as markdown, in reading order."""
    entry = get_report(results_dir, entry_id)
    directory = _entry_directory(results_dir, entry)
    if entry.source == "report":
        layout = _FINISHED_SECTIONS
    else:
        # A run folder keeps its sections one level down, under ``reports``.
        directory = directory / "reports"
        layout = _RUN_SECTIONS
    sections = []
    for path, title in _sections_in(directory, layout):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        sections.append({"title": title, "markdown": text})
    return sections


def compare_sections(results_dir: Path, left_id: str, right_id: str) -> list[dict]:
    """Two reports' sections paired by agent, for reading them side by side.

    Both entries are read in their own reading order and zipped on the agent
    title, so a section one report has and the other lacks is still shown —
    with the missing side empty rather than silently dropped.
    """
    left_rows = read_sections(results_dir, left_id)
    right_rows = read_sections(results_dir, right_id)
    left = {s["title"]: s["markdown"] for s in left_rows}
    right = {s["title"]: s["markdown"] for s in right_rows}
    titles = list(dict.fromkeys([s["title"] for s in left_rows] + [s["title"] for s in right_rows]))
    return [{"title": title, "left": left.get(title), "right": right.get(title)} for title in titles]


def report_file(results_dir: Path, entry_id: str, *, html: bool) -> Path:
    """The file to serve for an entry: its one-page HTML page or its markdown.

    Only a finished report has these on disk. An unfinished run's folder is read
    section by section instead (``read_sections``).
    """
    entry = get_report(results_dir, entry_id)
    if entry.source != "report":
        raise ArchivePathError("this report has no consolidated file")
    directory = _entry_directory(results_dir, entry)
    path = directory / ("complete_report.html" if html else "complete_report.md")
    if not path.is_file():
        raise ArchivePathError("the report file is gone")
    return path


def _deletable_directory(results_dir: Path, entry: ArchivedReport) -> Path:
    """The folder deleting ``entry`` removes, and nothing above it.

    A finished report owns its whole stamped folder. A run folder only owns the
    ``reports`` subfolder: the run's message log beside it is a separate record,
    so it survives, and the ticker folder is never removed from under it.
    """
    directory = _entry_directory(results_dir, entry)
    root = Path(results_dir).resolve()
    if entry.source != "report":
        return directory / "reports"
    if directory == root or (directory.parent == root and directory.name == "reports"):
        # `reports/` is the whole collection, not one report inside it.
        raise ArchivePathError("refusing to delete the results directory itself")
    return directory


def delete_report(results_dir: Path, entry_id: str) -> dict:
    """Remove one archived report from disk; return the ticker and what was removed.

    Only a path this module listed can be deleted, and only the entry's own
    folder inside the results directory, so a crafted id cannot reach anything
    else. The ticker directory is pruned when it is left empty, but a directory
    still holding other dates or logs is kept.
    """
    results_dir = Path(results_dir).resolve()
    entry = get_report(results_dir, entry_id)
    directory = _deletable_directory(results_dir, entry)

    removed = []
    # walk with followlinks=False: a symlink inside the tree is removed as a link,
    # never traversed, so deleting a report cannot reach outside its own folder.
    for current, dirnames, filenames in os.walk(directory, topdown=False, followlinks=False):
        here = Path(current)
        for name in filenames:
            path = here / name
            path.unlink(missing_ok=True)
            removed.append(path)
        for name in dirnames:
            path = here / name
            if path.is_symlink():
                path.unlink(missing_ok=True)
                removed.append(path)
                continue
            # Not empty: something this module does not own lives there.
            with contextlib.suppress(OSError):
                path.rmdir()
    with contextlib.suppress(OSError):
        directory.rmdir()

    # A finished report's ticker folder only ever held stamped reports; once its
    # last one is gone there is nothing to show, so prune it. A run folder's
    # parent keeps the run's log and other dates, so it is left alone.
    if entry.source == "report":
        parent = directory.parent
        if parent != results_dir and parent.name != "reports":
            with contextlib.suppress(OSError):
                parent.rmdir()

    return {
        "id": entry.id,
        "ticker": entry.ticker,
        "analysis_date": entry.analysis_date,
        "removed": [str(path.relative_to(results_dir)) for path in removed],
        "directory_removed": not directory.exists(),
    }
