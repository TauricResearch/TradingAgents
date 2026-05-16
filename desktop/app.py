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
from typing import Any

from nicegui import app, ui

from desktop.state.database import HistoryDB
from desktop.state.runner import EventKind, PipelineRunner, RunnerEvent

logger = logging.getLogger(__name__)

# ── Shared singletons (one per process) ─────────────────────────────────

_ASSETS = Path(__file__).parent / "assets"
db = HistoryDB()

# LEAK-02: Module-level reference so shutdown can join it.
# Set by analysis.py when a batch starts.
active_batch_runner: Any = None  # BatchRunner | None — avoid circular import

# Read watchdog timeout from user settings (defaults to 900s if not set)
_watchdog_timeout = int(db.get_setting("watchdog_timeout", "1200") or "1200")
runner = PipelineRunner(watchdog_timeout=_watchdog_timeout)

# ── v3 Feedback Loop services (lazy-started on first page load) ──────
from desktop.services.price_service import PriceService
from desktop.services.alert_engine import AlertEngine
from desktop.services.outcome_tracker import OutcomeTracker
from desktop.services.scheduler import Scheduler

price_service = PriceService(ttl_seconds=300)
alert_engine = AlertEngine(db=db, price_service=price_service)
outcome_tracker = OutcomeTracker(db=db, price_service=price_service)


def _scheduled_analysis_callback(
    tickers: list[str], schedule_id: int,
) -> None:
    """Callback invoked by the Scheduler when a schedule fires.

    Reads default config from settings and dispatches via BatchRunner
    (for multi-ticker) or PipelineRunner (for single ticker).
    """
    from desktop.state.batch import BatchRunner

    # Build config from saved settings (same defaults as analysis page)
    provider = db.get_setting("default_provider", "openai") or "openai"
    depth = int(db.get_setting("research_depth", "1") or "1")
    language = db.get_setting("output_language", "English") or "English"
    analysts_str = db.get_setting(
        "default_analysts", "market,social,news,fundamentals"
    ) or "market,social,news,fundamentals"
    selected_analysts = [a.strip() for a in analysts_str.split(",") if a.strip()]

    config: dict[str, Any] = {
        "llm_provider": provider,
        "max_debate_rounds": depth,
        "max_risk_discuss_rounds": depth,
        "output_language": language,
    }

    today = __import__("datetime").date.today().isoformat()

    if len(tickers) == 1:
        # Single ticker — use PipelineRunner directly
        analysis_id = db.insert_analysis(
            ticker=tickers[0],
            date=today,
            provider=provider,
            model=config.get("deep_think_llm", "default"),
            config=config,
            selected_analysts=selected_analysts,
        )
        runner.start(
            config=config,
            ticker=tickers[0],
            date=today,
            selected_analysts=selected_analysts,
            analysis_id=analysis_id,
        )
    else:
        # Multi-ticker — use BatchRunner
        batch = BatchRunner(runner=runner, db=db)
        batch.start(
            tickers=tickers,
            config=config,
            date=today,
            selected_analysts=selected_analysts,
        )


scheduler = Scheduler(
    db=db, runner=runner, run_analysis=_scheduled_analysis_callback,
)

# Mark any analyses stuck in "running" from a previous crashed session.
for _stale in db.list_analyses(status="running"):
    db.mark_interrupted(_stale.id)


# ── App-level persistence (CR-02) ─────────────────────────────────────
#
# These functions run from the pipeline thread's finally block via
# runner callbacks, so completion data is ALWAYS persisted — even if
# the user closed their tab or navigated to a different page.


def persist_reports(analysis_id: int, tracker: Any) -> None:
    """Save ProgressTracker report sections as .md files on disk.

    Creates ``~/.tradingagents/results/<id>/`` with one file per
    report section.  Sets ``result_dir`` on the database row.

    CR-01 fix: accepts ``analysis_id`` directly (captured from event
    payload) instead of reading ``runner.analysis_id`` which is
    mutable and may already point to the next ticker in batch mode.
    """
    snap = tracker.snapshot()
    sections = {k: v for k, v in snap.report_sections.items() if v}
    if not sections:
        logger.warning("No report sections to persist for analysis #%d", analysis_id)
        return

    result_dir = Path.home() / ".tradingagents" / "results" / str(analysis_id)
    result_dir.mkdir(parents=True, exist_ok=True)

    for key, content in sections.items():
        (result_dir / f"{key}.md").write_text(content, encoding="utf-8")

    db.update_result_dir(analysis_id, str(result_dir))
    logger.info("Persisted %d report sections to %s", len(sections), result_dir)

    # ── Approach C: Extract structured recommendation at write time ─────
    # The markdown format is known (just generated), so extraction is
    # highly reliable here. This populates the recommendations table
    # that the Dashboard, Scorecard, and Alerts features read from.
    _extract_recommendation_at_write(analysis_id, result_dir)


def _extract_recommendation_at_write(analysis_id: int, result_dir: Path) -> None:
    """Extract structured recommendation data from the just-written report.

    Called by persist_reports() right after markdown files are saved.
    Failures are logged but never propagated — the analysis is already
    persisted, so a failed extraction just means the dashboard won't
    show this recommendation until migration backfills it.
    """
    decision_path = result_dir / "final_trade_decision.md"
    if not decision_path.exists():
        logger.debug("No final_trade_decision.md for analysis #%d, skipping extraction", analysis_id)
        return

    try:
        from desktop.services.recommendation_extractor import extract_from_file

        # Get the ticker from the analysis row
        analysis = db.get_analysis(analysis_id)
        ticker = analysis.ticker if analysis else None

        rec = extract_from_file(decision_path, ticker=ticker, analysis_id=analysis_id)

        # Insert into recommendations table
        rec_id = db.insert_recommendation(
            analysis_id=analysis_id,
            ticker=rec.ticker or ticker or "UNKNOWN",
            verdict=rec.verdict,
            confidence=rec.confidence,
            price_at_analysis=rec.price_at_analysis,
            stop_loss=rec.stop_loss,
            entry_trigger=rec.entry_trigger,
            profit_target=rec.profit_target,
            review_date=rec.review_date,
            notes=rec.notes,
        )

        # Deactivate older recommendations for the same ticker
        effective_ticker = rec.ticker or ticker or "UNKNOWN"
        deactivated = db.deactivate_older_for_ticker(effective_ticker, keep_id=rec_id)
        if deactivated:
            logger.info(
                "Deactivated %d older recommendation(s) for %s",
                deactivated,
                effective_ticker,
            )

        logger.info(
            "Extracted recommendation #%d for %s: %s (stop=%s, entry=%s, target=%s)",
            rec_id,
            effective_ticker,
            rec.verdict,
            rec.stop_loss,
            rec.entry_trigger,
            rec.profit_target,
        )

        # Auto-create alerts for the new recommendation's price levels
        try:
            rec_row = db.get_recommendation(rec_id)
            if rec_row is not None:
                alert_count = alert_engine.create_alerts_for_recommendation(rec_row)
                if alert_count:
                    logger.info(
                        "Created %d alert(s) for %s recommendation #%d",
                        alert_count,
                        effective_ticker,
                        rec_id,
                    )
        except Exception:
            logger.exception("Failed to create alerts for recommendation #%d", rec_id)
    except Exception:
        logger.exception(
            "Failed to extract recommendation for analysis #%d — "
            "dashboard will backfill via migration",
            analysis_id,
        )


def flush_logs(analysis_id: int, tracker: Any) -> None:
    """Persist all log entries from the tracker to the database.

    CR-01 fix: accepts ``analysis_id`` directly (captured from event
    payload) instead of reading ``runner.analysis_id``.
    """
    snap = tracker.snapshot()
    count = db.flush_logs(analysis_id, snap.messages, snap.tool_calls)
    if count:
        logger.info("Flushed %d log entries for analysis #%d", count, analysis_id)


def on_pipeline_finished(event: RunnerEvent) -> None:
    """App-level handler — runs on the pipeline thread regardless of UI state.

    Persists reports, logs, and updates the analysis status in the DB.
    This guarantees no data loss even if the user navigated away or
    closed the browser tab.
    """
    # WR-05 + RACE-03: Read analysis_id ONLY from event payload (set at
    # capture time). Do NOT fall back to runner.analysis_id — in batch mode
    # the runner may already have a new ID for the next ticker.
    aid = None
    if isinstance(event.data, dict):
        aid = event.data.get("analysis_id")
    if not aid:
        logger.warning("on_pipeline_finished: event missing analysis_id, skipping persistence")
        return

    try:
        if event.kind == EventKind.COMPLETED:
            db.mark_completed(aid)
        elif event.kind == EventKind.FAILED:
            error_text = "Unknown error"
            if isinstance(event.data, dict):
                error_text = event.data.get("error", error_text)
            elif isinstance(event.data, str):
                error_text = event.data
            db.mark_failed(aid, error_text)
        elif event.kind == EventKind.CANCELLED:
            db.mark_interrupted(aid)

        persist_reports(aid, runner.tracker)
        flush_logs(aid, runner.tracker)
    except Exception:
        logger.exception("Failed to persist results for analysis #%d", aid)


# Register the callback on the runner so it fires from the pipeline thread.
runner.on_finished = on_pipeline_finished


# ── Layout ──────────────────────────────────────────────────────────────


def create_header(drawer_ref: ui.left_drawer) -> ui.label:
    """Top header bar with app title.

    Takes the page-local drawer reference to avoid the global (WR-03 fix).
    Returns the running badge label so the page can update it from its
    own timer instead of using bind_visibility_from (BUG-03 fix).
    """
    with ui.header().classes("bg-dark text-white items-center justify-between"):
        ui.button(icon="menu", on_click=lambda: drawer_ref.toggle()).props("flat color=white")
        ui.label("TradingAgents").classes("text-h6 q-ml-sm")
        ui.space()
        # BUG-03: Don't use bind_visibility_from on process-level singleton.
        # It causes N lock acquisitions per 100ms per connected tab.
        # Instead, page timers update this label's visibility explicitly.
        running_label = ui.label("Analysis Running").classes(
            "running-badge text-caption bg-green-8 text-white q-px-sm q-py-xs rounded-borders"
        )
        running_label.set_visibility(runner.is_running)
        return running_label


def create_drawer() -> ui.left_drawer:
    """Left navigation drawer with page links."""
    d = ui.left_drawer(value=True, bordered=True).classes("bg-dark")
    with d:
        ui.label("Navigation").classes("text-subtitle1 text-white q-pa-md")
        ui.separator().classes("bg-grey-8")

        with ui.column().classes("q-pa-sm gap-none"):
            _nav_item("New Analysis", "/", "analytics")
            _nav_item("Dashboard", "/dashboard", "dashboard")
            _nav_item("History", "/history", "history")
            _nav_item("Scorecard", "/scorecard", "leaderboard")
            _nav_item("Alerts", "/alerts", "notifications")
            _nav_item("Schedules", "/schedules", "schedule")
            _nav_item("Portfolio", "/portfolio", "account_balance_wallet")
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
    badge = _page_wrapper()
    from desktop.pages.analysis import render_analysis_page
    render_analysis_page(runner=runner, db=db, running_badge=badge)


@ui.page("/history")
def page_history() -> None:
    """History page — past analyses table."""
    badge = _page_wrapper()
    from desktop.pages.history import render_history_page
    render_history_page(db=db, runner=runner)
    _badge_timer(badge)


@ui.page("/logs")
def page_logs() -> None:
    """Logs page — debug log viewer."""
    badge = _page_wrapper()
    from desktop.pages.logs import render_logs_page
    render_logs_page(runner=runner)
    _badge_timer(badge)


@ui.page("/analysis/{analysis_id}")
def page_detail(analysis_id: int) -> None:
    """Detail page — view a completed analysis."""
    badge = _page_wrapper()
    from desktop.pages.detail import render_detail_page
    render_detail_page(db=db, analysis_id=analysis_id)
    _badge_timer(badge)


@ui.page("/compare/{id_a}/{id_b}")
def page_compare(id_a: int, id_b: int) -> None:
    """Compare page — side-by-side analysis comparison."""
    badge = _page_wrapper()
    from desktop.pages.compare import render_compare_page
    render_compare_page(db=db, id_a=id_a, id_b=id_b)
    _badge_timer(badge)


@ui.page("/settings")
def page_settings() -> None:
    """Settings page — user preferences."""
    badge = _page_wrapper()
    from desktop.pages.settings import render_settings_page
    render_settings_page(db=db)
    _badge_timer(badge)


@ui.page("/dashboard")
def page_dashboard() -> None:
    """Dashboard — active recommendations with live prices."""
    badge = _page_wrapper()
    from desktop.pages.dashboard import render_dashboard_page
    render_dashboard_page(db=db, price_service=price_service)
    _badge_timer(badge)


@ui.page("/scorecard")
def page_scorecard() -> None:
    """Scorecard — recommendation accuracy metrics."""
    badge = _page_wrapper()
    from desktop.pages.scorecard import render_scorecard_page
    render_scorecard_page(db=db)
    _badge_timer(badge)


@ui.page("/alerts")
def page_alerts() -> None:
    """Alerts — price level monitoring."""
    badge = _page_wrapper()
    from desktop.pages.alerts import render_alerts_page
    render_alerts_page(db=db, alert_engine=alert_engine)
    _badge_timer(badge)


@ui.page("/schedules")
def page_schedules() -> None:
    """Schedules — recurring pre-market analysis."""
    badge = _page_wrapper()
    from desktop.pages.schedules import render_schedules_page
    render_schedules_page(db=db, scheduler=scheduler)
    _badge_timer(badge)


@ui.page("/portfolio")
def page_portfolio() -> None:
    """Portfolio — position tracking + recommendation overlay."""
    badge = _page_wrapper()
    from desktop.pages.portfolio import render_portfolio_page
    render_portfolio_page(db=db, price_service=price_service)
    _badge_timer(badge)


def _badge_timer(badge: ui.label) -> None:
    """BUG-03: Lightweight timer to update the running badge on non-analysis pages."""
    def _update() -> None:
        badge.set_visibility(runner.is_running)
    ui.timer(2.0, _update)


def _page_wrapper() -> ui.label:
    """Common layout wrapper applied to every page.

    Returns the header running-badge label so pages can update its
    visibility from their own polling timer (BUG-03 fix).
    """
    ui.add_css(_ASSETS / "style.css")
    d = create_drawer()
    return create_header(d)


# ── App entry ───────────────────────────────────────────────────────────


def run_app(*, host: str = "127.0.0.1", port: int = 8080, reload: bool = False) -> None:
    """Start the NiceGUI desktop app."""
    # Start v3 background services
    alert_engine.start()
    outcome_tracker.start()
    scheduler.start()
    logger.info("v3 background services started (alert engine + outcome tracker + scheduler)")

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
    LEAK-02: Also join any active batch runner thread.
    """
    # Cancel and join batch runner first (it calls runner.start internally)
    if active_batch_runner is not None:
        try:
            active_batch_runner.cancel()
            active_batch_runner.join(timeout=5.0)
        except Exception:
            logger.exception("Failed to join batch runner on shutdown")

    # Stop v3 background services
    try:
        scheduler.stop()
        alert_engine.stop()
        outcome_tracker.stop()
        logger.info("v3 background services stopped")
    except Exception:
        logger.exception("Failed to stop v3 background services")

    if runner.is_running and runner.analysis_id is not None:
        db.mark_interrupted(runner.analysis_id)
        runner.cancel()
        runner.join(timeout=5.0)
