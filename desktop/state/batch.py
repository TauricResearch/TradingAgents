"""Batch runner — sequential multi-ticker analysis orchestrator.

Runs a list of tickers one at a time through ``PipelineRunner``,
tracking per-ticker outcomes. The UI polls ``snapshot()`` to render
the batch progress strip.

Design: The batch runner does NOT subclass or modify PipelineRunner.
It calls ``runner.start()`` for each ticker, waits for completion
via polling, and advances to the next. This keeps the single-ticker
path untouched.

See also: PLAN-features-v2.md, Feature 3.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from desktop.state.runner import PipelineRunner, RunnerEvent

logger = logging.getLogger(__name__)

_INTER_TICKER_DELAY = 2.0  # seconds between tickers to avoid rate limits


@dataclass
class BatchState:
    """Snapshot of batch progress — safe to read from any thread.

    Returned by ``BatchRunner.snapshot()``. All list fields are copies.
    """

    tickers: list[str] = field(default_factory=list)
    current_index: int = 0
    current_ticker: str = ""
    completed_tickers: list[str] = field(default_factory=list)
    failed_tickers: list[str] = field(default_factory=list)
    is_running: bool = False
    is_done: bool = False


class BatchRunner:
    """Orchestrates sequential multi-ticker analysis runs.

    Usage::

        batch = BatchRunner(runner=runner, db=db)
        batch.start(
            tickers=["AAPL", "MSFT", "NVDA"],
            config={...},
            date="2026-05-15",
            selected_analysts=["market", "news"],
        )

        # In ui.timer:
        state = batch.snapshot()  # thread-safe copy
    """

    def __init__(
        self,
        *,
        runner: PipelineRunner,
        db: Any,  # HistoryDB — avoid circular import
    ) -> None:
        self._runner = runner
        self._db = db
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._events: queue.Queue[RunnerEvent] = queue.Queue()

        # Mutable state — only written under lock (CR-01 fix)
        self._tickers: list[str] = []
        self._current_index: int = 0
        self._current_ticker: str = ""
        self._completed_tickers: list[str] = []
        self._failed_tickers: list[str] = []
        self._is_running: bool = False
        self._is_done: bool = False

    def snapshot(self) -> BatchState:
        """Return a thread-safe copy of the current batch state (CR-01 fix)."""
        with self._lock:
            return BatchState(
                tickers=list(self._tickers),
                current_index=self._current_index,
                current_ticker=self._current_ticker,
                completed_tickers=list(self._completed_tickers),
                failed_tickers=list(self._failed_tickers),
                is_running=self._is_running,
                is_done=self._is_done,
            )

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def start(
        self,
        *,
        tickers: list[str],
        config: dict[str, Any],
        date: str,
        selected_analysts: list[str],
    ) -> None:
        """Launch the batch run in a background thread."""
        with self._lock:
            if self._is_running:
                raise RuntimeError("Batch is already running")
            self._tickers = list(tickers)
            self._current_index = 0
            self._current_ticker = ""
            self._completed_tickers = []
            self._failed_tickers = []
            self._is_running = True
            self._is_done = False

        self._cancel_event.clear()

        self._thread = threading.Thread(
            target=self._run_batch,
            kwargs={
                "tickers": list(tickers),
                "config": config,
                "date": date,
                "selected_analysts": selected_analysts,
            },
            daemon=True,
            name="batch-runner",
        )
        self._thread.start()

    def cancel(self) -> None:
        """Cancel the batch run (finishes the current ticker, skips the rest)."""
        self._cancel_event.set()
        self._runner.cancel()

    def join(self, timeout: float | None = None) -> None:
        """Block until the batch thread finishes (LEAK-02 fix)."""
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def drain_events(self, max_events: int = 20) -> list[RunnerEvent]:
        """Drain batch-level events (completion per ticker)."""
        events: list[RunnerEvent] = []
        for _ in range(max_events):
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return events

    def _run_batch(
        self,
        *,
        tickers: list[str],
        config: dict[str, Any],
        date: str,
        selected_analysts: list[str],
    ) -> None:
        """Batch thread — runs tickers sequentially."""
        try:
            for i, ticker in enumerate(tickers):
                if self._cancel_event.is_set():
                    break

                with self._lock:
                    self._current_index = i
                    self._current_ticker = ticker
                logger.info("Batch: starting ticker %d/%d: %s", i + 1, len(tickers), ticker)

                # Insert DB row for this ticker
                try:
                    analysis_id = self._db.insert_analysis(
                        ticker=ticker,
                        date=date,
                        provider=config.get("llm_provider", ""),
                        model=config.get("deep_think_llm", "default"),
                        config=config,
                        selected_analysts=selected_analysts,
                    )
                except Exception:
                    logger.exception("Batch: failed to create DB row for %s", ticker)
                    with self._lock:
                        self._failed_tickers.append(ticker)
                    continue

                # WR-04 + BUG-04: Check cancel after DB insert, before starting
                # pipeline. Mark the just-inserted row as interrupted so it
                # doesn't stay "running" forever.
                if self._cancel_event.is_set():
                    try:
                        self._db.mark_interrupted(analysis_id)
                    except Exception:
                        logger.exception("Batch: failed to mark %d interrupted", analysis_id)
                    break

                # Start pipeline for this ticker
                try:
                    self._runner.start(
                        config=config,
                        ticker=ticker,
                        date=date,
                        selected_analysts=list(selected_analysts),
                        analysis_id=analysis_id,
                    )
                except RuntimeError as e:
                    logger.error("Batch: runner failed to start for %s: %s", ticker, e)
                    with self._lock:
                        self._failed_tickers.append(ticker)
                    continue

                # Wait for pipeline to finish
                self._wait_for_completion(ticker)

                # Brief pause between tickers
                if i < len(tickers) - 1 and not self._cancel_event.is_set():
                    time.sleep(_INTER_TICKER_DELAY)

        finally:
            with self._lock:
                self._current_index = len(self._completed_tickers)
                self._is_running = False
                self._is_done = True
            logger.info(
                "Batch complete: %d/%d succeeded, %d failed",
                len(self._completed_tickers),
                len(tickers),
                len(self._failed_tickers),
            )

    def _wait_for_completion(self, ticker: str) -> None:
        """Poll the runner until the current ticker finishes."""
        while self._runner.is_running:
            if self._cancel_event.is_set():
                self._runner.cancel()
            time.sleep(0.5)

        # WR-01: Wait for pipeline thread to fully exit (including on_finished)
        # so tracker isn't reset while persist_reports is still reading it.
        self._runner.join(timeout=10.0)

        # Check outcome
        status = self._runner.status
        with self._lock:
            if status == "completed":
                self._completed_tickers.append(ticker)
            else:
                self._failed_tickers.append(ticker)
