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


# ── Analyst status mapping (mirrors cli/main.py) ─────────────────────────

_ANALYST_ORDER = ["market", "social", "news", "fundamentals"]

_ANALYST_AGENT_NAMES: dict[str, str] = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}

_ANALYST_REPORT_MAP: dict[str, str] = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}


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


_WATCHDOG_TIMEOUT_DEFAULT = 900  # 15 minutes — Claude CLI calls can take 5+ min each


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

        # App-level completion callback (CR-02).
        # Called on the pipeline thread when the run finishes (any outcome).
        # Set by app.py at startup so persistence happens regardless of UI state.
        self.on_finished: Any | None = None  # Callable[[RunnerEvent], None]

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
        analysis_id: int | None = None,
        callbacks: list[Any] | None = None,
    ) -> None:
        """Launch the pipeline in a background thread.

        Parameters
        ----------
        analysis_id : int, optional
            Database row ID for this analysis. Set under the lock
            *before* the thread starts so ``on_finished`` always
            sees the correct ID (HI-01 race fix).

        Raises ``RuntimeError`` if a pipeline is already running.
        """
        with self._lock:
            if self._status == "running":
                raise RuntimeError("Pipeline is already running")
            self._status = "running"
            self._analysis_id = analysis_id  # set under lock before thread
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

    def join(self, timeout: float | None = None) -> None:
        """Block until the pipeline thread finishes (HI-03).

        Called during app shutdown so the ``on_finished`` callback has
        time to persist reports and logs before the process exits.
        """
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

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
        watchdog: _WatchdogTimer | None = None
        terminal_event: RunnerEvent | None = None
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
                self._process_chunk(chunk)
                self._queue.put(RunnerEvent(EventKind.CHUNK, chunk))

            final_state, decision = graph.propagate(
                ticker, date, on_chunk=on_chunk
            )

            # Check for late cancel
            if self._cancel_event.is_set():
                with self._lock:
                    self._status = "cancelled"
                terminal_event = RunnerEvent(EventKind.CANCELLED)
            else:
                with self._lock:
                    self._status = "completed"
                terminal_event = RunnerEvent(
                    EventKind.COMPLETED,
                    {"final_state": final_state, "decision": decision},
                )

        except _CancelledError:
            with self._lock:
                self._status = "cancelled"
            terminal_event = RunnerEvent(EventKind.CANCELLED)

        except Exception as exc:
            logger.exception("Pipeline failed for %s on %s", ticker, date)
            with self._lock:
                self._status = "failed"
            terminal_event = RunnerEvent(EventKind.FAILED, str(exc))

        finally:
            # Always stop watchdog
            if watchdog:
                watchdog.stop()

            # CR-02: Always call the app-level persistence callback.
            # This runs on the pipeline thread, so DB writes happen
            # even if the user closed the browser tab.
            if terminal_event is not None:
                if self.on_finished:
                    try:
                        self.on_finished(terminal_event)
                    except Exception:
                        logger.exception("on_finished callback failed")

                # Queue the event for the UI (if it's still listening)
                self._queue.put(terminal_event)

    # ── Chunk processing (mirrors cli/main.py logic) ─────────────────

    def _process_chunk(self, chunk: dict[str, Any]) -> None:
        """Extract messages, agent statuses, and reports from a LangGraph chunk.

        Runs on the pipeline thread.  All writes go through the
        thread-safe ProgressTracker so the UI can read snapshots safely.
        """
        # 1. Extract messages from the chunk
        for message in chunk.get("messages", []):
            msg_id = getattr(message, "id", None)
            if msg_id is not None and self._tracker.has_seen_message(msg_id):
                continue

            msg_type, content = _classify_message(message)
            if content and content.strip():
                self._tracker.add_message(msg_type, content)

            if hasattr(message, "tool_calls") and message.tool_calls:
                for tc in message.tool_calls:
                    name = tc["name"] if isinstance(tc, dict) else tc.name
                    args = tc["args"] if isinstance(tc, dict) else tc.args
                    self._tracker.add_tool_call(name, args)

        # 2. Update analyst statuses based on report keys in chunk
        # WR-01: use snapshot() instead of accessing private _selected_analysts
        snap = self._tracker.snapshot()
        selected = snap.selected_analysts
        found_active = False
        for analyst_key in _ANALYST_ORDER:
            if analyst_key not in selected:
                continue
            agent_name = _ANALYST_AGENT_NAMES[analyst_key]
            report_key = _ANALYST_REPORT_MAP[analyst_key]

            if chunk.get(report_key):
                self._tracker.update_report_section(report_key, chunk[report_key])

            has_report = bool(snap.report_sections.get(report_key))
            if has_report:
                self._tracker.update_agent_status(agent_name, "completed")
            elif not found_active:
                self._tracker.update_agent_status(agent_name, "in_progress")
                found_active = True

        if not found_active and selected:
            if snap.agent_status.get("Bull Researcher") == "pending":
                self._tracker.update_agent_status("Bull Researcher", "in_progress")

        # 3. Research team (investment debate)
        # CR-03: accumulate bull/bear/judge into one combined section
        debate = chunk.get("investment_debate_state")
        if debate:
            bull = (debate.get("bull_history") or "").strip()
            bear = (debate.get("bear_history") or "").strip()
            judge = (debate.get("judge_decision") or "").strip()
            if bull or bear:
                for agent in ("Bull Researcher", "Bear Researcher", "Research Manager"):
                    self._tracker.update_agent_status(agent, "in_progress")

            parts: list[str] = []
            if bull:
                parts.append(f"### Bull Researcher\n{bull}")
            if bear:
                parts.append(f"### Bear Researcher\n{bear}")
            if judge:
                parts.append(f"### Research Manager Decision\n{judge}")
            if parts:
                self._tracker.update_report_section(
                    "investment_plan", "\n\n".join(parts),
                )

            if judge:
                for agent in ("Bull Researcher", "Bear Researcher", "Research Manager"):
                    self._tracker.update_agent_status(agent, "completed")
                self._tracker.update_agent_status("Trader", "in_progress")

        # 4. Trading team
        if chunk.get("trader_investment_plan"):
            self._tracker.update_report_section(
                "trader_investment_plan", chunk["trader_investment_plan"],
            )
            self._tracker.update_agent_status("Trader", "completed")
            self._tracker.update_agent_status("Aggressive Analyst", "in_progress")

        # 5. Risk management team (CR-NEW-01/02/03: aligned with cli/main.py)
        risk = chunk.get("risk_debate_state")
        if risk:
            agg = (risk.get("aggressive_history") or "").strip()
            con = (risk.get("conservative_history") or "").strip()
            neu = (risk.get("neutral_history") or "").strip()
            judge_r = (risk.get("judge_decision") or "").strip()

            # WR-02: take a fresh snapshot — the one from step 2 is stale
            # after all the update_agent_status calls in steps 2-4.
            snap_status = self._tracker.snapshot().agent_status

            risk_parts: list[str] = []
            if agg:
                if snap_status.get("Aggressive Analyst") != "completed":
                    self._tracker.update_agent_status("Aggressive Analyst", "in_progress")
                risk_parts.append(f"### Aggressive Analyst\n{agg}")
            if con:
                if snap_status.get("Conservative Analyst") != "completed":
                    self._tracker.update_agent_status("Conservative Analyst", "in_progress")
                risk_parts.append(f"### Conservative Analyst\n{con}")
            if neu:
                if snap_status.get("Neutral Analyst") != "completed":
                    self._tracker.update_agent_status("Neutral Analyst", "in_progress")
                risk_parts.append(f"### Neutral Analyst\n{neu}")
            if judge_r:
                risk_parts.append(f"### Portfolio Manager Decision\n{judge_r}")
                for agent in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"):
                    self._tracker.update_agent_status(agent, "completed")
                self._tracker.update_agent_status("Portfolio Manager", "in_progress")

            if risk_parts:
                self._tracker.update_report_section(
                    "final_trade_decision", "\n\n".join(risk_parts),
                )

        # 6. Portfolio manager final decision (top-level key from PM node)
        if chunk.get("final_trade_decision"):
            self._tracker.update_report_section(
                "final_trade_decision", chunk["final_trade_decision"],
            )
            self._tracker.update_agent_status("Portfolio Manager", "completed")

    def _on_watchdog_timeout(self) -> None:
        """Called by the watchdog when inactivity exceeds the threshold."""
        logger.warning("Watchdog: pipeline inactive for %ds, signalling cancel", self._watchdog_timeout)
        self._queue.put(RunnerEvent(EventKind.WATCHDOG, "Inactivity timeout"))
        self._cancel_event.set()


# ── Internal helpers ────────────────────────────────────────────────────


def _classify_message(message: Any) -> tuple[str, str | None]:
    """Classify a LangChain message into a display type and content string."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    raw = getattr(message, "content", None)
    # Extract string from list-of-dicts content (vision messages etc.)
    if isinstance(raw, list):
        parts = [p.get("text", "") for p in raw if isinstance(p, dict) and "text" in p]
        content = "\n".join(parts) if parts else None
    elif isinstance(raw, str) and raw.strip():
        content = raw
    else:
        content = None

    if isinstance(message, HumanMessage):
        if content and content.strip() == "Continue":
            return ("Control", content)
        return ("User", content)
    if isinstance(message, ToolMessage):
        return ("Data", content)
    if isinstance(message, AIMessage):
        return ("Agent", content)
    return ("System", content)


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
