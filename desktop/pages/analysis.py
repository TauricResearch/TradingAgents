"""Analysis page — two-state form + live progress dashboard.

**Pre-run state:** Configuration form (ticker, provider, analysts, date).
**Running state:** Form collapses to summary; progress dashboard expands.

See also: PLAN-desktop.md, F1 + F2.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

from nicegui import ui

import desktop.app as _app_module  # LEAK-02: register batch runner
from desktop.components.agent_card import AgentStatusPanel
from desktop.components.batch_progress import BatchProgressPanel
from desktop.components.log_panel import LogPanel
from desktop.components.price_chart import PriceChart
from desktop.components.progress_bar import ProgressPanel
from desktop.components.report_section import ReportSectionsPanel
from desktop.state.batch import BatchRunner
from desktop.state.database import HistoryDB
from desktop.state.runner import EventKind, PipelineRunner
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
from tradingagents.progress import REPORT_SECTIONS

# Provider options for the dropdown (display, key, url)
_PROVIDERS: list[tuple[str, str, str | None]] = [
    ("Claude CLI (Max, $0)", "claude_cli", None),
    ("OpenAI", "openai", "https://api.openai.com/v1"),
    ("Google", "google", None),
    ("Anthropic", "anthropic", "https://api.anthropic.com/"),
    ("xAI", "xai", "https://api.x.ai/v1"),
    ("DeepSeek", "deepseek", "https://api.deepseek.com"),
    ("Ollama", "ollama", "http://localhost:11434"),
    ("OpenRouter", "openrouter", "https://openrouter.ai/api/v1"),
]

_ANALYSTS = [
    ("Market Analyst", "market"),
    ("Sentiment Analyst", "social"),
    ("News Analyst", "news"),
    ("Fundamentals Analyst", "fundamentals"),
]

# Claude CLI models (not in the shared model catalog).
# IDs must match the Anthropic versioned format (claude-opus-4-6, not
# date-pinned snapshots like claude-opus-4-20250514 which is Opus 4 base).
_CLAUDE_CLI_MODELS: dict[str, list[tuple[str, str]]] = {
    "quick": [
        ("Claude Opus 4.7 — Latest frontier", "claude-opus-4-7"),
        ("Claude Opus 4.6 — Frontier intelligence", "claude-opus-4-6"),
        ("Claude Sonnet 4.6 — Fast + smart balance", "claude-sonnet-4-6"),
    ],
    "deep": [
        ("Claude Opus 4.7 — Latest frontier", "claude-opus-4-7"),
        ("Claude Opus 4.6 — Frontier intelligence", "claude-opus-4-6"),
    ],
}

_LANGUAGES: list[tuple[str, str]] = [
    ("English", "English"),
    ("中文 (Chinese)", "Chinese"),
    ("日本語 (Japanese)", "Japanese"),
    ("한국어 (Korean)", "Korean"),
    ("हिंदी (Hindi)", "Hindi"),
    ("Español (Spanish)", "Spanish"),
    ("Português (Portuguese)", "Portuguese"),
    ("Français (French)", "French"),
    ("Deutsch (German)", "German"),
    ("العربية (Arabic)", "Arabic"),
    ("Русский (Russian)", "Russian"),
    ("Custom", "custom"),
]


# WR-02: Ticker symbol validation (letters, digits, dots, dashes, carets)
_TICKER_RE = re.compile(r"^[A-Z0-9.\-^]{1,20}$")


def _get_models_for_provider(
    provider_key: str, mode: str,
) -> list[tuple[str, str]]:
    """Return model options for a provider and mode (no 'custom' entries)."""
    if provider_key == "claude_cli":
        return _CLAUDE_CLI_MODELS.get(mode, [])
    models = MODEL_OPTIONS.get(provider_key, {}).get(mode, [])
    return [(name, mid) for name, mid in models if mid != "custom"]


def render_analysis_page(
    *,
    runner: PipelineRunner,
    db: HistoryDB,
    running_badge: Any = None,
) -> None:
    """Render the analysis page content."""
    page = _AnalysisPage(runner=runner, db=db, running_badge=running_badge)
    page.build()


class _AnalysisPage:
    """Internal page controller managing form and progress states."""

    def __init__(
        self, *, runner: PipelineRunner, db: HistoryDB, running_badge: Any = None,
    ) -> None:
        self._runner = runner
        self._db = db

        # WR-04: Read saved defaults from settings DB so the form
        # reflects what the user configured on the Settings page.
        saved = db.get_all_settings()

        saved_provider = saved.get("default_provider", "claude_cli")
        saved_analysts_csv = saved.get(
            "default_analysts", "market,social,news,fundamentals"
        )
        saved_analysts = [
            a.strip() for a in saved_analysts_csv.split(",") if a.strip()
        ]
        saved_depth = int(saved.get("research_depth", "1"))

        # Form state — seeded from saved settings
        self._provider_key = saved_provider
        self._backend_url: str | None = next(
            (url for _, key, url in _PROVIDERS if key == saved_provider), None
        )
        self._selected_analysts: list[str] = saved_analysts or [
            "market", "social", "news", "fundamentals"
        ]
        self._research_depth = saved_depth
        self._quick_model_id: str | None = "claude-opus-4-7"
        self._deep_model_id: str | None = "claude-opus-4-7"
        self._language: str = "English"

        # UI refs — form inputs (read .value directly to avoid stale state)
        self._ticker_input: ui.input | None = None
        self._date_input: ui.input | None = None
        self._quick_model_select: ui.select | None = None
        self._deep_model_select: ui.select | None = None
        self._language_select: ui.select | None = None
        self._custom_language_input: ui.input | None = None
        self._page_root: ui.column | None = None
        self._summary_strip: ui.row | None = None
        self._agent_panel: AgentStatusPanel | None = None
        self._progress_panel: ProgressPanel | None = None
        self._log_panel: LogPanel | None = None
        self._report_panel: ReportSectionsPanel | None = None
        self._timer: ui.timer | None = None

        # Run button ref for RACE-01 (disable on click)
        self._run_btn: ui.button | None = None
        # Header running badge for BUG-03 (manual visibility update)
        self._running_badge: ui.label | None = running_badge

        # Batch mode state
        self._batch_mode: bool = False
        self._batch_runner: BatchRunner | None = None
        self._batch_panel: BatchProgressPanel | None = None
        self._watchlist_select: ui.select | None = None

    def build(self) -> None:
        """Render the full page layout."""
        self._page_root = ui.column().classes("w-full")
        with self._page_root:
            if self._runner.is_running:
                self._build_progress_view()
                self._start_polling()
            else:
                self._build_form()

    # ── Form (pre-run state) ────────────────────────────────────────

    def _build_form(self) -> None:
        """Render the configuration form."""
        with ui.column().classes("w-full max-w-2xl mx-auto q-pa-md gap-md"):
            ui.label("New Analysis").classes("text-h5 text-white")
            ui.label(
                "Configure and run a trading analysis. The pipeline takes 5-15 minutes."
            ).classes("text-body2 text-grey-5")

            with ui.card().classes("w-full"):
                # Batch mode toggle
                with ui.row().classes("items-center gap-sm q-mb-sm"):
                    ui.switch(
                        "Batch Mode (multiple tickers)",
                        value=False,
                        on_change=lambda e: self._toggle_batch_mode(e.value),
                    ).props("color=purple dense")

                # Ticker — read .value directly in _on_run to avoid stale state
                self._ticker_input = ui.input(
                    "Ticker Symbol",
                    value="SPY",
                    placeholder="e.g. SPY, AAPL, 0700.HK",
                ).classes("w-full").props("outlined dense")

                # Watchlist selector (only visible in batch mode)
                watchlists = self._db.list_watchlists()
                wl_options = {name: ", ".join(tickers) for name, tickers in watchlists.items()}
                self._watchlist_select = ui.select(
                    label="Load Watchlist",
                    options=list(wl_options.keys()) if wl_options else ["No saved watchlists"],
                    on_change=lambda e: self._load_watchlist(e.value),
                ).classes("w-full q-mt-xs").props("outlined dense clearable")
                self._watchlist_select.set_visibility(False)

                # Date
                self._date_input = ui.input(
                    "Analysis Date",
                    value=datetime.date.today().isoformat(),
                ).classes("w-full q-mt-sm").props("outlined dense")
                with self._date_input:
                    with ui.menu() as menu:
                        ui.date(
                            value=datetime.date.today().isoformat(),
                            on_change=lambda e: (
                                self._date_input.set_value(e.value),
                                menu.close(),
                            ),
                        ).props("today-btn")
                    with self._date_input.add_slot("append"):
                        ui.icon("event").on("click", menu.open).classes("cursor-pointer")

                # Provider — WR-04: initial value from saved settings
                provider_options = {display: key for display, key, _ in _PROVIDERS}
                provider_display = next(
                    (d for d, k in provider_options.items() if k == self._provider_key),
                    "Claude CLI (Max, $0)",
                )
                ui.select(
                    label="LLM Provider",
                    options=list(provider_options.keys()),
                    value=provider_display,
                    on_change=lambda e: self._on_provider_change(e.value, provider_options),
                ).classes("w-full q-mt-sm").props("outlined dense")

                # Language selector
                lang_options = {display: key for display, key in _LANGUAGES}
                self._language_select = ui.select(
                    label="Output Language",
                    options=list(lang_options.keys()),
                    value="English",
                    on_change=lambda e: self._on_language_change(
                        e.value, lang_options,
                    ),
                ).classes("w-full q-mt-sm").props("outlined dense")

                self._custom_language_input = ui.input(
                    "Custom Language",
                    placeholder="e.g. Turkish, Vietnamese, …",
                ).classes("w-full q-mt-xs").props("outlined dense")
                self._custom_language_input.set_visibility(False)

                # Model selectors (quick + deep think)
                ui.label("Model Configuration").classes(
                    "text-subtitle2 q-mt-md"
                )

                quick_models = _get_models_for_provider(
                    self._provider_key, "quick",
                )
                quick_opts = {d: m for d, m in quick_models}
                self._quick_model_select = ui.select(
                    label="Quick Think Model",
                    options=list(quick_opts.keys()),
                    value=next(iter(quick_opts), None),
                    on_change=lambda e: self._on_quick_model_change(e.value),
                ).classes("w-full q-mt-xs").props("outlined dense")
                self._quick_model_select.set_visibility(bool(quick_opts))

                deep_models = _get_models_for_provider(
                    self._provider_key, "deep",
                )
                deep_opts = {d: m for d, m in deep_models}
                self._deep_model_select = ui.select(
                    label="Deep Think Model",
                    options=list(deep_opts.keys()),
                    value=next(iter(deep_opts), None),
                    on_change=lambda e: self._on_deep_model_change(e.value),
                ).classes("w-full q-mt-xs").props("outlined dense")
                self._deep_model_select.set_visibility(bool(deep_opts))

                # Analysts (checkboxes) — WR-04: pre-checked from saved settings
                ui.label("Analyst Team").classes("text-subtitle2 q-mt-md")
                with ui.row().classes("gap-md"):
                    for display, key in _ANALYSTS:
                        ui.checkbox(
                            display,
                            value=key in self._selected_analysts,
                            on_change=lambda e, k=key: self._toggle_analyst(k, e.value),
                        )

                # Research depth — WR-04: initial value from saved settings
                ui.label("Research Depth").classes("text-subtitle2 q-mt-md")
                ui.slider(
                    min=1, max=3, step=1, value=self._research_depth,
                    on_change=lambda e: setattr(self, "_research_depth", int(e.value)),
                ).classes("w-full").props("label-always markers snap")

            # Run button — save ref for RACE-01 (disable on click)
            self._run_btn = ui.button(
                "Run Analysis",
                icon="play_arrow",
                on_click=self._on_run,
            ).classes("w-full q-mt-md").props("color=green size=lg")

    def _on_provider_change(self, display_name: str, mapping: dict[str, str]) -> None:
        self._provider_key = mapping.get(display_name, "claude_cli")
        self._backend_url = next(
            (url for d, _, url in _PROVIDERS if d == display_name), None
        )
        # Refresh both model selectors from catalog
        self._refresh_model_select(self._quick_model_select, "quick", "_quick_model_id")
        self._refresh_model_select(self._deep_model_select, "deep", "_deep_model_id")

    def _refresh_model_select(
        self, select: ui.select | None, mode: str, attr: str,
    ) -> None:
        """Repopulate a model dropdown after the provider changed."""
        if select is None:
            return
        models = _get_models_for_provider(self._provider_key, mode)
        options = {display: mid for display, mid in models}
        select.options = list(options.keys())
        if options:
            first = next(iter(options))
            select.set_value(first)
            setattr(self, attr, options[first])
        else:
            select.set_value(None)
            setattr(self, attr, None)
        select.set_visibility(bool(options))
        select.update()

    def _on_quick_model_change(self, display_name: str | None) -> None:
        models = _get_models_for_provider(self._provider_key, "quick")
        model_map = {d: m for d, m in models}
        self._quick_model_id = model_map.get(display_name or "") if display_name else None

    def _on_deep_model_change(self, display_name: str | None) -> None:
        models = _get_models_for_provider(self._provider_key, "deep")
        model_map = {d: m for d, m in models}
        self._deep_model_id = model_map.get(display_name or "") if display_name else None

    def _on_language_change(
        self, display_name: str, mapping: dict[str, str],
    ) -> None:
        value = mapping.get(display_name, "English")
        if value == "custom":
            self._language = "custom"
            if self._custom_language_input:
                self._custom_language_input.set_visibility(True)
        else:
            self._language = value
            if self._custom_language_input:
                self._custom_language_input.set_visibility(False)

    def _toggle_analyst(self, key: str, checked: bool) -> None:
        if checked and key not in self._selected_analysts:
            self._selected_analysts.append(key)
        elif not checked and key in self._selected_analysts:
            self._selected_analysts.remove(key)

    def _toggle_batch_mode(self, enabled: bool) -> None:
        """Switch between single-ticker and batch mode."""
        self._batch_mode = enabled
        if self._ticker_input:
            if enabled:
                self._ticker_input.props("label='Tickers (comma-separated)'")
                self._ticker_input.props(
                    "placeholder='e.g. SPY, AAPL, MSFT, NVDA, TSLA'"
                )
            else:
                self._ticker_input.props("label='Ticker Symbol'")
                self._ticker_input.props("placeholder='e.g. SPY, AAPL, 0700.HK'")
        if self._watchlist_select:
            self._watchlist_select.set_visibility(enabled)

    def _load_watchlist(self, name: str | None) -> None:
        """Populate the ticker input from a saved watchlist."""
        if not name or not self._ticker_input:
            return
        watchlists = self._db.list_watchlists()
        tickers = watchlists.get(name, [])
        if tickers:
            self._ticker_input.set_value(", ".join(tickers))

    def _build_config(self) -> dict[str, Any]:
        """Build config dict from current form state."""
        language = self._language
        if language == "custom" and self._custom_language_input:
            language = (self._custom_language_input.value or "").strip()
        if not language or language == "custom":
            language = "English"

        config: dict[str, Any] = {
            "llm_provider": self._provider_key,
            "backend_url": self._backend_url,
            "max_debate_rounds": self._research_depth,
            "max_risk_discuss_rounds": self._research_depth,
            "output_language": language,
        }
        if self._quick_model_id:
            config["quick_think_llm"] = self._quick_model_id
        if self._deep_model_id:
            config["deep_think_llm"] = self._deep_model_id
        return config

    async def _on_run(self) -> None:
        """Validate and start the analysis pipeline (single or batch)."""
        # RACE-01: Disable button immediately to prevent double-submission
        if self._run_btn:
            self._run_btn.disable()

        raw_ticker = (self._ticker_input.value or "").strip().upper() if self._ticker_input else ""
        date = (self._date_input.value or "") if self._date_input else ""

        if not raw_ticker:
            ui.notify("Please enter a ticker symbol", type="warning")
            if self._run_btn:
                self._run_btn.enable()
            return
        if not self._selected_analysts:
            ui.notify("Select at least one analyst", type="warning")
            if self._run_btn:
                self._run_btn.enable()
            return

        # WR-03: Validate date format
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            ui.notify("Invalid date format. Use YYYY-MM-DD.", type="warning")
            if self._run_btn:
                self._run_btn.enable()
            return

        config = self._build_config()

        # Batch mode: parse comma-separated tickers
        if self._batch_mode:
            tickers = [t.strip() for t in raw_ticker.split(",") if t.strip()]
            if len(tickers) < 2:
                ui.notify("Batch mode needs at least 2 tickers", type="warning")
                if self._run_btn:
                    self._run_btn.enable()
                return
            if len(tickers) > 20:
                ui.notify("Maximum 20 tickers per batch", type="warning")
                if self._run_btn:
                    self._run_btn.enable()
                return
            # WR-02: Validate each ticker
            invalid = [t for t in tickers if not _TICKER_RE.match(t)]
            if invalid:
                ui.notify(f"Invalid ticker(s): {', '.join(invalid)}", type="warning")
                if self._run_btn:
                    self._run_btn.enable()
                return

            self._batch_runner = BatchRunner(runner=self._runner, db=self._db)
            # LEAK-02: Register on app module so shutdown can join it
            _app_module.active_batch_runner = self._batch_runner
            try:
                self._batch_runner.start(
                    tickers=tickers,
                    config=config,
                    date=date,
                    selected_analysts=list(self._selected_analysts),
                )
            except RuntimeError as e:
                ui.notify(str(e), type="negative")
                if self._run_btn:
                    self._run_btn.enable()
                return

            self._run_ticker = tickers[0]
            self._run_date = date

            if self._page_root:
                self._page_root.clear()
                with self._page_root:
                    self._build_batch_progress_view(tickers)
                    self._start_batch_polling()
                    ui.notify(
                        f"Batch started: {len(tickers)} tickers", type="positive",
                    )
            return

        # Single ticker mode (original flow)
        ticker = raw_ticker

        # WR-02: Validate ticker format
        if not _TICKER_RE.match(ticker):
            ui.notify(f"Invalid ticker format: {ticker}", type="warning")
            if self._run_btn:
                self._run_btn.enable()
            return

        # WR-06: Insert into database with error handling
        try:
            analysis_id = self._db.insert_analysis(
                ticker=ticker,
                date=date,
                provider=self._provider_key,
                model=config.get("deep_think_llm", "default"),
                config=config,
                selected_analysts=self._selected_analysts,
            )
        except Exception as e:
            logger.exception("Failed to create analysis record")
            ui.notify(f"Database error: {e}", type="negative")
            if self._run_btn:
                self._run_btn.enable()
            return

        # Store ticker/date for the progress view summary strip
        self._run_ticker = ticker
        self._run_date = date

        # Start the pipeline — pass analysis_id so it's set under the lock
        # before the thread spawns (HI-01 race fix)
        try:
            self._runner.start(
                config=config,
                ticker=ticker,
                date=date,
                selected_analysts=list(self._selected_analysts),
                analysis_id=analysis_id,
            )
        except RuntimeError as e:
            # RACE-01: Mark the orphaned DB row as interrupted
            self._db.mark_interrupted(analysis_id)
            ui.notify(str(e), type="negative")
            if self._run_btn:
                self._run_btn.enable()
            return

        # Swap form → progress view inside the persistent root container
        if self._page_root:
            self._page_root.clear()
            with self._page_root:
                self._build_progress_view()
                self._start_polling()
                ui.notify(f"Analysis started for {ticker}", type="positive")

    # ── Progress view (running state) ───────────────────────────────

    def _build_progress_view(self) -> None:
        """Render the live progress dashboard.

        WR-01: On browser refresh, ``_run_ticker`` isn't set because
        ``_on_run`` never ran in this page instance.  Fall back to the
        database row so the user sees the real ticker, not "???".
        """
        ticker = getattr(self, "_run_ticker", None)
        date = getattr(self, "_run_date", None)

        if not ticker and self._runner.analysis_id:
            row = self._db.get_analysis(self._runner.analysis_id)
            if row:
                ticker = row.ticker
                date = row.date

        ticker = ticker or "???"
        date = date or ""

        with ui.column().classes("w-full q-pa-md gap-md"):
            # Summary strip
            with ui.row().classes(
                "items-center w-full bg-dark q-pa-sm rounded-borders"
            ):
                ui.icon("analytics").classes("text-green text-h5")
                ui.label(ticker).classes("text-h6 text-white q-ml-sm")
                ui.label(date).classes("text-caption text-grey q-ml-sm")
                ui.label(self._provider_key).classes("text-caption text-grey q-ml-sm")
                ui.space()
                ui.button(
                    "Cancel",
                    icon="stop",
                    on_click=self._on_cancel,
                ).props("color=red flat dense")

            # Price chart (renders once, not polled)
            if ticker and ticker != "???":
                PriceChart(ticker=ticker, analysis_date=date or "").build()

            # Two-column layout
            with ui.row().classes("w-full gap-md"):
                # Left column: agent status + progress bar
                with ui.column().classes("w-1/3 gap-md"):
                    self._progress_panel = ProgressPanel()
                    self._progress_panel.build()
                    self._progress_panel.start()

                    self._agent_panel = AgentStatusPanel()
                    self._agent_panel.build()

                # Right column: reports + log
                with ui.column().classes("w-2/3 gap-md"):
                    # Report sections
                    snap = self._runner.tracker.snapshot()
                    section_keys = list(snap.report_sections.keys())
                    self._report_panel = ReportSectionsPanel()
                    self._report_panel.build(section_keys)

                    # Log panel
                    self._log_panel = LogPanel()
                    self._log_panel.build()

    def _start_polling(self) -> None:
        """Start the UI timer that polls runner events and updates components."""
        self._timer = ui.timer(0.25, self._poll)

    def _poll(self) -> None:
        """Called every 250ms by the UI timer."""
        # Drain events from the runner queue
        for event in self._runner.drain_events():
            if event.kind == EventKind.COMPLETED:
                self._on_completed(event.data)
            elif event.kind == EventKind.FAILED:
                # WR-05: event.data is now a dict with analysis_id + error
                if isinstance(event.data, dict):
                    error_text = event.data.get("error", "Unknown error")
                else:
                    error_text = str(event.data) if event.data else "Unknown error"
                self._on_failed(error_text)
            elif event.kind == EventKind.CANCELLED:
                self._on_cancelled()
            elif event.kind == EventKind.WATCHDOG:
                ui.notify(
                    f"Pipeline stalled: {event.data}. Consider restarting.",
                    type="warning",
                    timeout=10000,
                )

        # Update UI components from tracker snapshot
        snap = self._runner.tracker.snapshot()
        total = self._runner.tracker.get_total_reports_count()

        if self._agent_panel:
            self._agent_panel.update(snap)
        if self._progress_panel:
            self._progress_panel.update(snap, total_reports=total)
        if self._log_panel:
            self._log_panel.update(snap)
        if self._report_panel:
            self._report_panel.update(snap)

        # BUG-03: Update header badge from page timer instead of bind_visibility
        if self._running_badge:
            self._running_badge.set_visibility(self._runner.is_running)

    def _on_cancel(self) -> None:
        self._runner.cancel()
        ui.notify("Cancelling analysis...", type="info")

    def _on_completed(self, data: dict[str, Any]) -> None:
        """Pipeline finished — UI-side handler.

        Persistence (DB status, reports, logs) is handled by the
        app-level ``on_pipeline_finished`` callback in app.py, which
        runs on the pipeline thread regardless of UI state.  This
        handler only manages UI updates and notifications.
        """
        if self._timer:
            self._timer.deactivate()
        ui.notify("Analysis completed!", type="positive", timeout=10000)
        self._safe_final_poll()

    def _on_failed(self, error_text: str) -> None:
        """Pipeline failed — UI notification only."""
        if self._timer:
            self._timer.deactivate()
        ui.notify(f"Analysis failed: {error_text}", type="negative", timeout=15000)
        self._safe_final_poll()

    def _on_cancelled(self) -> None:
        """Pipeline cancelled — UI notification only."""
        if self._timer:
            self._timer.deactivate()
        ui.notify("Analysis cancelled", type="warning")
        self._safe_final_poll()

    def _safe_final_poll(self) -> None:
        """WR-04: Best-effort final UI update, safe if page navigated away."""
        try:
            if self._page_root and self._agent_panel:
                self._poll()
        except Exception:
            # WR-07: log at WARNING (was DEBUG) — aids debugging
            logger.warning("Final poll skipped (page likely navigated away)", exc_info=True)

    # ── Batch progress view ────────────────────────────────────────────

    def _build_batch_progress_view(self, tickers: list[str]) -> None:
        """Render the batch-level progress + per-ticker dashboard."""
        with ui.column().classes("w-full q-pa-md gap-md"):
            # Batch header
            with ui.row().classes(
                "items-center w-full bg-dark q-pa-sm rounded-borders"
            ):
                ui.icon("playlist_play").classes("text-purple text-h5")
                ui.label("Batch Analysis").classes("text-h6 text-white q-ml-sm")
                ui.label(f"{len(tickers)} tickers").classes(
                    "text-caption text-grey q-ml-sm"
                )
                ui.space()
                ui.button(
                    "Cancel All", icon="stop",
                    on_click=self._on_batch_cancel,
                ).props("color=red flat dense")

            # Batch-level progress strip
            self._batch_panel = BatchProgressPanel()
            self._batch_panel.build(tickers)

            # Per-ticker progress (reuses existing components)
            self._progress_panel = ProgressPanel()
            self._progress_panel.build()
            self._progress_panel.start()

            self._agent_panel = AgentStatusPanel()
            self._agent_panel.build()

            self._log_panel = LogPanel()
            self._log_panel.build()

            # Save watchlist prompt
            with ui.row().classes("items-center gap-sm q-mt-sm"):
                wl_name_input = ui.input(
                    "Save as watchlist", placeholder="e.g. Tech Stocks",
                ).props("outlined dense").classes("w-48")

                async def save_wl() -> None:
                    name = (wl_name_input.value or "").strip()
                    if not name:
                        ui.notify("Enter a watchlist name", type="warning")
                        return
                    # WR-04: Catch ValueError from save_watchlist validation
                    # (rejects empty, >100 chars, or names with : \n etc.)
                    try:
                        self._db.save_watchlist(name, tickers)
                        ui.notify(f"Watchlist '{name}' saved!", type="positive")
                    except ValueError as e:
                        ui.notify(str(e), type="warning")

                ui.button("Save", icon="bookmark", on_click=save_wl).props(
                    "flat dense color=purple"
                )

    def _start_batch_polling(self) -> None:
        """Start the UI timer for batch mode."""
        self._timer = ui.timer(0.5, self._batch_poll)

    def _batch_poll(self) -> None:
        """Called every 500ms during batch runs.

        LEAK-01: Wrapped in try/except so navigating away doesn't cause
        exceptions from updating destroyed page elements.
        """
        if not self._batch_runner:
            return

        try:
            state = self._batch_runner.snapshot()

            # Update batch-level progress
            if self._batch_panel:
                if state.is_done:
                    self._batch_panel.mark_complete(
                        len(state.completed_tickers), len(state.tickers),
                    )
                else:
                    self._batch_panel.update(
                        current_index=len(state.completed_tickers),
                        total=len(state.tickers),
                        current_ticker=state.current_ticker,
                        completed_tickers=state.completed_tickers,
                        failed_tickers=state.failed_tickers,
                    )

            # Update per-ticker progress (same as single mode)
            snap = self._runner.tracker.snapshot()
            total = self._runner.tracker.get_total_reports_count()

            if self._agent_panel:
                self._agent_panel.update(snap)
            if self._progress_panel:
                self._progress_panel.update(snap, total_reports=total)
            if self._log_panel:
                self._log_panel.update(snap)

            # BUG-03: Update header badge
            if self._running_badge:
                self._running_badge.set_visibility(self._runner.is_running)
        except Exception:
            # LEAK-01: Page likely navigated away; deactivate timer
            logger.warning("Batch poll skipped (page likely navigated away)", exc_info=True)
            if self._timer:
                self._timer.deactivate()
            return

        # Batch done?
        if state.is_done:
            # WR-03: Clear stale batch runner reference so shutdown
            # doesn't try to join an already-finished runner and GC
            # can reclaim the BatchRunner + its internal queue.
            _app_module.active_batch_runner = None
            if self._timer:
                self._timer.deactivate()
            ok = len(state.completed_tickers)
            fail = len(state.failed_tickers)
            msg = f"Batch complete: {ok} succeeded"
            if fail:
                msg += f", {fail} failed"
            ui.notify(msg, type="positive" if not fail else "warning", timeout=10000)

    def _on_batch_cancel(self) -> None:
        """Cancel the entire batch run."""
        if self._batch_runner:
            self._batch_runner.cancel()
        ui.notify("Cancelling batch...", type="info")
