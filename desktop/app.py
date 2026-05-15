"""NiceGUI application scaffold with left-drawer navigation.

Provides the shared layout (header + left drawer + page slot) and
wires up page routing.  Each page module registers itself via
``@ui.page``.

Also hosts the **app-level completion handler** that persists reports
and logs regardless of which page the user is on (CR-02 fix).

Run with:  ``python -m desktop``
"""

from __future__ import annotations

import logging
from pathlib import Path

from nicegui import app, ui

from desktop.state.database import HistoryDB
from desktop.state.runner import EventKind, PipelineRunner, RunnerEvent

logger = logging.getLogger(__name__)

# ── Shared singletons (one per process) ─────────────────────────────────

_ASSETS = Path(__file__).parent / "assets"
db = HistoryDB()

# Read watchdog timeout from user settings (defaults to 900s if not set)
_watchdog_timeout = int(db.get_setting("watchdog_timeout", "1200") or "1200")
runner = PipelineRunner(watchdog_timeout=_watchdog_timeout)

# Mark any analyses stuck in "running" from a previous crashed session.
for _stale in db.list_analyses(status="running"):
    db.mark_interrupted(_stale.id)


# ── App-level persistence (CR-02) ─────────────────────────────────────
#
# These functions run from the pipeline thread's finally block via
# runner callbacks, so completion data is ALWAYS persisted — even if
# the user closed their tab or navigated to a different page.


def persist_reports(runner_ref: PipelineRunner) -> None:
    """Save ProgressTracker report sections as .md files on disk.

    Creates ``~/.tradingagents/results/<id>/`` with one file per
    report section.  Sets ``result_dir`` on the database row.
    """
    aid = runner_ref.analysis_id
    if not aid:
        return
    snap = runner_ref.tracker.snapshot()
    sections = {k: v for k, v in snap.report_sections.items() if v}
    if not sections:
        logger.warning("No report sections to persist for analysis #%d", aid)
        return

    result_dir = Path.home() / ".tradingagents" / "results" / str(aid)
    result_dir.mkdir(parents=True, exist_ok=True)

    for key, content in sections.items():
        (result_dir / f"{key}.md").write_text(content, encoding="utf-8")

    db.update_result_dir(aid, str(result_dir))
    logger.info("Persisted %d report sections to %s", len(sections), result_dir)


def flush_logs(runner_ref: PipelineRunner) -> None:
    """Persist all log entries from the tracker to the database."""
    aid = runner_ref.analysis_id
    if not aid:
        return
    snap = runner_ref.tracker.snapshot()
    count = db.flush_logs(aid, snap.messages, snap.tool_calls)
    if count:
        logger.info("Flushed %d log entries for analysis #%d", count, aid)


def on_pipeline_finished(event: RunnerEvent) -> None:
    """App-level handler — runs on the pipeline thread regardless of UI state.

    Persists reports, logs, and updates the analysis status in the DB.
    This guarantees no data loss even if the user navigated away or
    closed the browser tab.
    """
    aid = runner.analysis_id
    if not aid:
        return

    try:
        if event.kind == EventKind.COMPLETED:
            db.mark_completed(aid)
        elif event.kind == EventKind.FAILED:
            db.mark_failed(aid, str(event.data) if event.data else "Unknown error")
        elif event.kind == EventKind.CANCELLED:
            db.mark_interrupted(aid)

        persist_reports(runner)
        flush_logs(runner)
    except Exception:
        logger.exception("Failed to persist results for analysis #%d", aid)


# Register the callback on the runner so it fires from the pipeline thread.
runner.on_finished = on_pipeline_finished


# ── Layout ──────────────────────────────────────────────────────────────


def create_header(drawer_ref: ui.left_drawer) -> None:
    """Top header bar with app title.

    Takes the page-local drawer reference to avoid the global (WR-03 fix).
    """
    with ui.header().classes("bg-dark text-white items-center justify-between"):
        ui.button(icon="menu", on_click=lambda: drawer_ref.toggle()).props("flat color=white")
        ui.label("TradingAgents").classes("text-h6 q-ml-sm")
        ui.space()
        # Running badge — visible only when pipeline is active
        running_label = ui.label("Analysis Running").classes(
            "running-badge text-caption bg-green-8 text-white q-px-sm q-py-xs rounded-borders"
        )
        running_label.bind_visibility_from(runner, "is_running")


def create_drawer() -> ui.left_drawer:
    """Left navigation drawer with page links."""
    d = ui.left_drawer(value=True, bordered=True).classes("bg-dark")
    with d:
        ui.label("Navigation").classes("text-subtitle1 text-white q-pa-md")
        ui.separator().classes("bg-grey-8")

        with ui.column().classes("q-pa-sm gap-none"):
            _nav_item("New Analysis", "/", "analytics")
            _nav_item("History", "/history", "history")
            _nav_item("Logs", "/logs", "article")
            _nav_item("Settings", "/settings", "settings")

        ui.separator().classes("bg-grey-8 q-mt-auto")
        ui.label("TradingAgents Desktop").classes(
            "text-caption text-grey-6 q-pa-md"
        )

    return d


def _nav_item(label: str, target: str, icon: str) -> None:
    """Single navigation item in the drawer."""
    with ui.item(on_click=lambda: ui.navigate.to(target)).classes("text-white"):
        with ui.item_section().props("avatar"):
            ui.icon(icon).classes("text-grey-4")
        with ui.item_section():
            ui.label(label)


# ── Page scaffolding ────────────────────────────────────────────────────


@ui.page("/")
def page_analysis() -> None:
    """Analysis page — form + live progress."""
    _page_wrapper()
    from desktop.pages.analysis import render_analysis_page
    render_analysis_page(runner=runner, db=db)


@ui.page("/history")
def page_history() -> None:
    """History page — past analyses table."""
    _page_wrapper()
    from desktop.pages.history import render_history_page
    render_history_page(db=db)


@ui.page("/logs")
def page_logs() -> None:
    """Logs page — debug log viewer."""
    _page_wrapper()
    from desktop.pages.logs import render_logs_page
    render_logs_page(runner=runner)


@ui.page("/analysis/{analysis_id}")
def page_detail(analysis_id: int) -> None:
    """Detail page — view a completed analysis."""
    _page_wrapper()
    from desktop.pages.detail import render_detail_page
    render_detail_page(db=db, analysis_id=analysis_id)


@ui.page("/settings")
def page_settings() -> None:
    """Settings page — user preferences."""
    _page_wrapper()
    from desktop.pages.settings import render_settings_page
    render_settings_page(db=db)


def _page_wrapper() -> None:
    """Common layout wrapper applied to every page."""
    ui.add_css(_ASSETS / "style.css")
    d = create_drawer()
    create_header(d)


# ── App entry ───────────────────────────────────────────────────────────


def run_app(*, host: str = "127.0.0.1", port: int = 8080, reload: bool = False) -> None:
    """Start the NiceGUI desktop app."""
    app.on_shutdown(lambda: _cleanup())
    ui.run(
        title="TradingAgents",
        host=host,
        port=port,
        reload=reload,
        dark=True,
        native=False,  # Use browser window; set True for native window later
        favicon=None,
    )


def _cleanup() -> None:
    """Graceful shutdown — mark any running analysis as interrupted.

    HI-03: Join the pipeline thread so ``on_finished`` has time to
    persist reports and logs before the process exits.
    """
    if runner.is_running and runner.analysis_id is not None:
        db.mark_interrupted(runner.analysis_id)
        runner.cancel()
        runner.join(timeout=5.0)
