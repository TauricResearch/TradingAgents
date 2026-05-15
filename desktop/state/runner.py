"""Pipeline runner — manages the analysis thread lifecycle.

Wraps ``TradingAgentsGraph`` in a dedicated ``threading.Thread`` so the
NiceGUI event loop stays responsive.  Communicates results back via a
``queue.Queue`` that the UI polls with ``ui.timer(0.25)``.

Key features
------------
- **on_chunk streaming** via ``propagate(on_chunk=...)``
- **Watchdog** — kills the thread and auto-retries when no activity for
  ``watchdog_timeout`` seconds (F8/F9)
- **Status lifecycle** — idle → running → completed / failed / cancelled
- **Thread safety** — public API is safe to call from any thread

See also: PLAN-desktop.md, Phase 2.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.progress import ProgressTracker

logger = logging.getLogger(__name__)


# ── Event types pushed onto the queue ───────────────────────────────────


class EventKind(Enum):
    """Discriminator for events on the runner's output queue."""

    CHUNK = "chunk"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WATCHDOG = "watchdog"


@dataclass(frozen=True)
class RunnerEvent:
    """Immutable event produced by the pipeline thread."""

    kind: EventKind
    data: Any = None  # chunk dict, final_state, error string, etc.


# ── Runner ──────────────────────────────────────────────────────────────


_WATCHDOG_TIMEOUT_DEFAULT = 300  # 5 minutes


class PipelineRunner:
    """Manages the pipeline thread and exposes events via a queue.

    Usage (from NiceGUI page)::

        runner = PipelineRunner()
        runner.start(config={...}, ticker="AAPL", date="2026-05-14",
                     selected_analysts=["market", "news"])

        # In ui.timer(0.25):
        for event in runner.drain_events():
            if event.kind == EventKind.CHUNK:
                process_chunk(event.data)
            elif event.kind == EventKind.COMPLETED:
                show_result(event.data)

    Parameters
    ----------
    watchdog_timeout : float
        Seconds of inactivity before the watchdog kills the pipeline
        and enqueues a ``WATCHDOG`` event. Set to 0 to disable.
    """

    def __init__(self, watchdog_timeout: float = _WATCHDOG_TIMEOUT_DEFAULT) -> None:
        self._lock = threading.Lock()
        self._queue: queue.Queue[RunnerEvent] = queue.Queue()
        self._tracker = ProgressTracker()
        self._thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._watchdog_timeout = watchdog_timeout

        # Public read-only state
        self._status: str = "idle"  # idle | running | completed | failed | cancelled
        self._analysis_id: int | None = None

    # ── Properties ──────────────────────────────────────────────────

    @property
    def tracker(self) -> ProgressTracker:
        """The shared progress tracker (safe to read from any thread)."""
        return self._tracker

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._status == "running"

    @property
    def analysis_id(self) -> int | None:
        """Database row ID of the current/last analysis, if set."""
        with self._lock:
            return self._analysis_id

    @analysis_id.setter
    def analysis_id(self, value: int | None) -> None:
        with self._lock:
            self._analysis_id = value

    # ── Public API ──────────────────────────────────────────────────

    def start(
        self,
        *,
        config: dict[str, Any],
        ticker: str,
        date: str,
        selected_analysts: list[str],
        callbacks: list[Any] | None = None,
    ) -> None:
        """Launch the pipeline in a background thread.

        Raises ``RuntimeError`` if a pipeline is already running.
        """
        with self._lock:
            if self._status == "running":
                raise RuntimeError("Pipeline is already running")
            self._status = "running"
            self._cancel_event.clear()

        # Reset tracker for the new run
        self._tracker.init_for_analysis(selected_analysts)

        self._thread = threading.Thread(
            target=self._run,
            kwargs={
                "config": config,
                "ticker": ticker,
                "date": date,
                "selected_analysts": selected_analysts,
                "callbacks": callbacks or [],
            },
            daemon=True,
            name=f"pipeline-{ticker}-{date}",
        )
        self._thread.start()

    def cancel(self) -> None:
        """Request cancellation of the running pipeline.

        The pipeline thread checks ``_cancel_event`` between chunks and
        exits early. This is a *cooperative* cancel — if the pipeline
        is stuck inside a single LLM call, the watchdog handles it.
        """
        self._cancel_event.set()

    def drain_events(self, max_events: int = 50) -> list[RunnerEvent]:
        """Non-blocking drain of queued events (call from UI timer)."""
        events: list[RunnerEvent] = []
        for _ in range(max_events):
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    # ── Pipeline thread ─────────────────────────────────────────────

    def _run(
        self,
        *,
        config: dict[str, Any],
        ticker: str,
        date: str,
        selected_analysts: list[str],
        callbacks: list[Any],
    ) -> None:
        """Entry point for the pipeline thread. Must not touch UI."""
        try:
            # Desktop always enables checkpointing (F9)
            run_config = {**DEFAULT_CONFIG, **config, "checkpoint_enabled": True}

            graph = TradingAgentsGraph(
                selected_analysts,
                config=run_config,
                debug=False,
                callbacks=callbacks,
            )

            # Start watchdog if configured
            watchdog: _WatchdogTimer | None = None
            if self._watchdog_timeout > 0:
                watchdog = _WatchdogTimer(
                    tracker=self._tracker,
                    timeout=self._watchdog_timeout,
                    cancel_event=self._cancel_event,
                    on_timeout=self._on_watchdog_timeout,
                )
                watchdog.start()

            def on_chunk(chunk: dict[str, Any]) -> None:
                """Callback invoked by propagate() for each streamed chunk."""
                if self._cancel_event.is_set():
                    raise _CancelledError("Analysis cancelled by user")
                self._queue.put(RunnerEvent(EventKind.CHUNK, chunk))

            final_state, decision = graph.propagate(
                ticker, date, on_chunk=on_chunk
            )

            if watchdog:
                watchdog.stop()

            # Check for late cancel
            if self._cancel_event.is_set():
                with self._lock:
                    self._status = "cancelled"
                self._queue.put(RunnerEvent(EventKind.CANCELLED))
                return

            with self._lock:
                self._status = "completed"
            self._queue.put(
                RunnerEvent(EventKind.COMPLETED, {"final_state": final_state, "decision": decision})
            )

        except _CancelledError:
            if watchdog:  # type: ignore[possibly-undefined]
                watchdog.stop()
            with self._lock:
                self._status = "cancelled"
            self._queue.put(RunnerEvent(EventKind.CANCELLED))

        except Exception as exc:
            if watchdog:  # type: ignore[possibly-undefined]
                watchdog.stop()
            logger.exception("Pipeline failed for %s on %s", ticker, date)
            with self._lock:
                self._status = "failed"
            self._queue.put(RunnerEvent(EventKind.FAILED, str(exc)))

    def _on_watchdog_timeout(self) -> None:
        """Called by the watchdog when inactivity exceeds the threshold."""
        logger.warning("Watchdog: pipeline inactive for %ds, signalling cancel", self._watchdog_timeout)
        self._queue.put(RunnerEvent(EventKind.WATCHDOG, "Inactivity timeout"))
        self._cancel_event.set()


# ── Internal helpers ────────────────────────────────────────────────────


class _CancelledError(Exception):
    """Raised inside the pipeline thread to unwind on cancellation."""


class _WatchdogTimer:
    """Background thread that monitors ProgressTracker activity.

    If ``seconds_since_last_activity()`` exceeds ``timeout``, the
    ``on_timeout`` callback is invoked (which typically sets the
    cancel event).
    """

    def __init__(
        self,
        *,
        tracker: ProgressTracker,
        timeout: float,
        cancel_event: threading.Event,
        on_timeout: Any,
        poll_interval: float = 10.0,
    ) -> None:
        self._tracker = tracker
        self._timeout = timeout
        self._cancel_event = cancel_event
        self._on_timeout = on_timeout
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll, daemon=True, name="watchdog"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _poll(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self._poll_interval)
            if self._stop_event.is_set() or self._cancel_event.is_set():
                return

            secs = self._tracker.seconds_since_last_activity()
            if secs is not None and secs > self._timeout:
                self._on_timeout()
                return
