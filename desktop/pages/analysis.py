"""Analysis page — two-state form + live progress dashboard.

**Pre-run state:** Configuration form (ticker, provider, analysts, date).
**Running state:** Form collapses to summary; progress dashboard expands.

See also: PLAN-desktop.md, F1 + F2.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from nicegui import ui

from desktop.components.agent_card import AgentStatusPanel
from desktop.components.log_panel import LogPanel
from desktop.components.progress_bar import ProgressPanel
from desktop.components.report_section import ReportSectionsPanel
from desktop.state.database import HistoryDB
from desktop.state.runner import EventKind, PipelineRunner
from tradingagents.default_config import DEFAULT_CONFIG
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


def render_analysis_page(*, runner: PipelineRunner, db: HistoryDB) -> None:
    """Render the analysis page content."""
    page = _AnalysisPage(runner=runner, db=db)
    page.build()


class _AnalysisPage:
    """Internal page controller managing form and progress states."""

    def __init__(self, *, runner: PipelineRunner, db: HistoryDB) -> None:
        self._runner = runner
        self._db = db

        # Form state
        self._ticker = "SPY"
        self._date = datetime.date.today().isoformat()
        self._provider_key = "claude_cli"
        self._backend_url: str | None = None
        self._selected_analysts: list[str] = ["market", "social", "news", "fundamentals"]
        self._research_depth = 1

        # UI refs
        self._form_container: ui.column | None = None
        self._progress_container: ui.column | None = None
        self._summary_strip: ui.row | None = None
        self._agent_panel: AgentStatusPanel | None = None
        self._progress_panel: ProgressPanel | None = None
        self._log_panel: LogPanel | None = None
        self._report_panel: ReportSectionsPanel | None = None
        self._timer: ui.timer | None = None

    def build(self) -> None:
        """Render the full page layout."""
        # If already running, show progress state
        if self._runner.is_running:
            self._build_progress_view()
            self._start_polling()
            return

        self._build_form()

    # ── Form (pre-run state) ────────────────────────────────────────

    def _build_form(self) -> None:
        """Render the configuration form."""
        self._form_container = ui.column().classes("w-full max-w-2xl mx-auto q-pa-md gap-md")
        with self._form_container:
            ui.label("New Analysis").classes("text-h5 text-white")
            ui.label(
                "Configure and run a trading analysis. The pipeline takes 5-15 minutes."
            ).classes("text-body2 text-grey-5")

            with ui.card().classes("w-full"):
                # Ticker
                ticker_input = ui.input(
                    "Ticker Symbol",
                    value=self._ticker,
                    placeholder="e.g. SPY, AAPL, 0700.HK",
                ).classes("w-full").props("outlined dense")
                ticker_input.on("update:model-value", lambda e: setattr(self, "_ticker", e.args))

                # Date
                date_input = ui.input(
                    "Analysis Date",
                    value=self._date,
                ).classes("w-full q-mt-sm").props("outlined dense")
                with date_input:
                    with ui.menu() as menu:
                        ui.date(
                            value=self._date,
                            on_change=lambda e: (
                                setattr(self, "_date", e.value),
                                date_input.set_value(e.value),
                                menu.close(),
                            ),
                        ).props("today-btn")
                    with date_input.add_slot("append"):
                        ui.icon("event").on("click", menu.open).classes("cursor-pointer")

                # Provider
                provider_options = {display: key for display, key, _ in _PROVIDERS}
                provider_select = ui.select(
                    label="LLM Provider",
                    options=list(provider_options.keys()),
                    value="Claude CLI (Max, $0)",
                ).classes("w-full q-mt-sm").props("outlined dense")
                provider_select.on(
                    "update:model-value",
                    lambda e: self._on_provider_change(e.args, provider_options),
                )

                # Analysts (checkboxes)
                ui.label("Analyst Team").classes("text-subtitle2 q-mt-md")
                with ui.row().classes("gap-md"):
                    for display, key in _ANALYSTS:
                        ui.checkbox(
                            display,
                            value=True,
                            on_change=lambda e, k=key: self._toggle_analyst(k, e.value),
                        )

                # Research depth
                ui.label("Research Depth").classes("text-subtitle2 q-mt-md")
                ui.slider(
                    min=1, max=3, step=1, value=1,
                    on_change=lambda e: setattr(self, "_research_depth", int(e.value)),
                ).classes("w-full").props("label-always markers snap")

            # Run button
            ui.button(
                "Run Analysis",
                icon="play_arrow",
                on_click=self._on_run,
            ).classes("w-full q-mt-md").props("color=green size=lg")

    def _on_provider_change(self, display_name: str, mapping: dict[str, str]) -> None:
        self._provider_key = mapping.get(display_name, "claude_cli")
        self._backend_url = next(
            (url for d, _, url in _PROVIDERS if d == display_name), None
        )

    def _toggle_analyst(self, key: str, checked: bool) -> None:
        if checked and key not in self._selected_analysts:
            self._selected_analysts.append(key)
        elif not checked and key in self._selected_analysts:
            self._selected_analysts.remove(key)

    async def _on_run(self) -> None:
        """Validate and start the analysis pipeline."""
        ticker = self._ticker.strip().upper()
        if not ticker:
            ui.notify("Please enter a ticker symbol", type="warning")
            return
        if not self._selected_analysts:
            ui.notify("Select at least one analyst", type="warning")
            return

        config: dict[str, Any] = {
            "llm_provider": self._provider_key,
            "backend_url": self._backend_url,
            "max_debate_rounds": self._research_depth,
            "max_risk_discuss_rounds": self._research_depth,
        }

        # For Claude CLI, set models
        if self._provider_key == "claude_cli":
            config["quick_think_llm"] = "claude-opus-4-20250514"
            config["deep_think_llm"] = "claude-opus-4-20250514"

        # Insert into database
        analysis_id = self._db.insert_analysis(
            ticker=ticker,
            date=self._date,
            provider=self._provider_key,
            model=config.get("deep_think_llm", "default"),
            config=config,
            selected_analysts=self._selected_analysts,
        )
        self._runner.analysis_id = analysis_id

        # Start the pipeline
        try:
            self._runner.start(
                config=config,
                ticker=ticker,
                date=self._date,
                selected_analysts=list(self._selected_analysts),
            )
        except RuntimeError as e:
            ui.notify(str(e), type="negative")
            return

        # Switch to progress view
        if self._form_container:
            self._form_container.clear()
            self._form_container.delete()

        self._build_progress_view()
        self._start_polling()
        ui.notify(f"Analysis started for {ticker}", type="positive")

    # ── Progress view (running state) ───────────────────────────────

    def _build_progress_view(self) -> None:
        """Render the live progress dashboard."""
        self._progress_container = ui.column().classes("w-full q-pa-md gap-md")
        with self._progress_container:
            # Summary strip
            self._summary_strip = ui.row().classes(
                "items-center w-full bg-dark q-pa-sm rounded-borders"
            )
            with self._summary_strip:
                ui.icon("analytics").classes("text-green text-h5")
                ui.label(f"{self._ticker}").classes("text-h6 text-white q-ml-sm")
                ui.label(f"{self._date}").classes("text-caption text-grey q-ml-sm")
                ui.label(f"{self._provider_key}").classes("text-caption text-grey q-ml-sm")
                ui.space()
                ui.button(
                    "Cancel",
                    icon="stop",
                    on_click=self._on_cancel,
                ).props("color=red flat dense")

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
                self._on_failed(event.data)
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

    def _on_cancel(self) -> None:
        self._runner.cancel()
        ui.notify("Cancelling analysis...", type="info")

    def _on_completed(self, data: dict[str, Any]) -> None:
        """Pipeline finished successfully."""
        if self._timer:
            self._timer.deactivate()
        if self._runner.analysis_id:
            self._db.mark_completed(self._runner.analysis_id)
        ui.notify("Analysis completed!", type="positive", timeout=10000)
        # Final UI update
        self._poll()

    def _on_failed(self, error_text: str) -> None:
        """Pipeline failed with an error."""
        if self._timer:
            self._timer.deactivate()
        if self._runner.analysis_id:
            self._db.mark_failed(self._runner.analysis_id, error_text)
        ui.notify(f"Analysis failed: {error_text}", type="negative", timeout=15000)

    def _on_cancelled(self) -> None:
        """Pipeline was cancelled."""
        if self._timer:
            self._timer.deactivate()
        if self._runner.analysis_id:
            self._db.mark_interrupted(self._runner.analysis_id)
        ui.notify("Analysis cancelled", type="warning")
