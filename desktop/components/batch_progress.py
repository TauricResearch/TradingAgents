"""Batch progress strip for multi-ticker analysis runs.

Shows which ticker is currently being analyzed, how many are done,
and provides a cancel-all button.

See also: PLAN-features-v2.md, Feature 3.
"""

from __future__ import annotations

from nicegui import ui


class BatchProgressPanel:
    """Batch-level progress indicator above the per-ticker dashboard.

    Call ``update()`` from the UI timer with the current batch state.
    """

    def __init__(self) -> None:
        self._progress: ui.linear_progress | None = None
        self._label: ui.label | None = None
        self._ticker_chips: ui.row | None = None

    def build(self, tickers: list[str]) -> None:
        """Render the batch progress strip."""
        with ui.card().classes("w-full ta-batch-progress"):
            with ui.row().classes("items-center w-full"):
                ui.icon("playlist_play").classes("text-purple text-h6")
                ui.label("Batch Analysis").classes("text-subtitle1")
                ui.space()
                self._label = ui.label(
                    f"0 / {len(tickers)} tickers"
                ).classes("text-caption text-grey")

            self._progress = ui.linear_progress(
                value=0, show_value=False,
            ).classes("q-mt-sm").props("color=purple size=8px rounded")

            # Ticker chips — show status of each ticker
            self._ticker_chips = ui.row().classes("gap-xs q-mt-sm flex-wrap")
            with self._ticker_chips:
                for ticker in tickers:
                    # WR-05: Removed unused data-ticker attribute that had
                    # no JS consumer and posed a defense-in-depth gap if
                    # called without prior ticker validation.
                    ui.label(ticker).classes(
                        "text-caption text-white bg-grey-8 q-px-sm q-py-xs rounded-borders"
                    )

    def update(
        self,
        *,
        current_index: int,
        total: int,
        current_ticker: str,
        completed_tickers: list[str],
        failed_tickers: list[str],
    ) -> None:
        """Refresh the batch progress strip."""
        fraction = current_index / max(total, 1)
        if self._progress:
            self._progress.set_value(fraction)
        if self._label:
            self._label.set_text(
                f"{current_index} / {total} tickers — now: {current_ticker}"
            )

    def mark_complete(self, completed: int, total: int) -> None:
        """Final state — all done."""
        if self._progress:
            self._progress.set_value(1.0)
        if self._label:
            self._label.set_text(f"{completed} / {total} tickers complete")
