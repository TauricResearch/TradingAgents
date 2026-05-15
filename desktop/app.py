"""NiceGUI application scaffold with left-drawer navigation.

Provides the shared layout (header + left drawer + page slot) and
wires up page routing.  Each page module registers itself via
``@ui.page``.

Run with:  ``python -m desktop``
"""

from __future__ import annotations

from pathlib import Path

from nicegui import app, ui

from desktop.state.database import HistoryDB
from desktop.state.runner import PipelineRunner

# ── Shared singletons (one per process) ─────────────────────────────────

_ASSETS = Path(__file__).parent / "assets"
db = HistoryDB()
runner = PipelineRunner()


# ── Layout ──────────────────────────────────────────────────────────────


def create_header() -> None:
    """Top header bar with app title."""
    with ui.header().classes("bg-dark text-white items-center justify-between"):
        ui.button(icon="menu", on_click=lambda: drawer.toggle()).props("flat color=white")
        ui.label("TradingAgents").classes("text-h6 q-ml-sm")
        ui.space()
        # Running badge — visible only when pipeline is active
        running_label = ui.label("Analysis Running").classes(
            "running-badge text-caption bg-green-8 text-white q-px-sm q-py-xs rounded-borders"
        )
        running_label.bind_visibility_from(runner, "is_running")


def create_drawer() -> ui.left_drawer:
    """Left navigation drawer with page links."""
    drawer = ui.left_drawer(value=True, bordered=True).classes("bg-dark")
    with drawer:
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

    return drawer


def _nav_item(label: str, target: str, icon: str) -> None:
    """Single navigation item in the drawer."""
    with ui.item(on_click=lambda: ui.navigate.to(target)).classes("text-white"):
        with ui.item_section().props("avatar"):
            ui.icon(icon).classes("text-grey-4")
        with ui.item_section():
            ui.label(label)


# ── Page scaffolding ────────────────────────────────────────────────────

# Module-level drawer reference so create_header can toggle it.
drawer: ui.left_drawer


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


@ui.page("/settings")
def page_settings() -> None:
    """Settings page — user preferences."""
    _page_wrapper()
    from desktop.pages.settings import render_settings_page
    render_settings_page(db=db)


def _page_wrapper() -> None:
    """Common layout wrapper applied to every page."""
    global drawer
    ui.add_css(_ASSETS / "style.css")
    create_header()
    drawer = create_drawer()


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
    """Graceful shutdown — mark any running analysis as interrupted."""
    if runner.is_running and runner.analysis_id is not None:
        db.mark_interrupted(runner.analysis_id)
        runner.cancel()
