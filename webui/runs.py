"""Running analyses for the UI: one worker, a queue, and a replayable event log.

The graph is synchronous and long-running, so a run cannot happen inside a
request. Each run is queued and executed on a single background worker, and its
stream is turned into events the browser reads over SSE.

One worker, not a pool. A run costs real money at the provider and the whole
point of the book view is queueing a dozen tickers at once; running those in
parallel would multiply the spend per minute and collide with provider rate
limits, so they go one at a time and the queue is visible in the UI.

Every event is retained per run, so a browser that connects late or reloads
replays the run from the beginning instead of joining a stream already past the
analyst reports.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from cli.display import classify_message_type
from cli.models import AnalystType, AssetType
from cli.prompts import detect_asset_type, filter_analysts_for_asset_type
from cli.stats_handler import StatsCallbackHandler
from tradingagents.agents.rating import is_review, run_rating
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from webui.paths import tilde

logger = logging.getLogger(__name__)

# The report fields a run fills, keyed by the state field so a chunk maps
# straight onto a panel.
REPORT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("market_report", "Market Analyst"),
    ("sentiment_report", "Sentiment Analyst"),
    ("news_report", "News Analyst"),
    ("fundamentals_report", "Fundamentals Analyst"),
    ("investment_plan", "Research Manager"),
    ("trader_investment_plan", "Trader"),
    ("final_trade_decision", "Portfolio Manager"),
)

# The debate histories, which live inside a nested state field rather than
# being state fields of their own, so a run emits them under keys of its own
# making. Named here so the UI labels them as the reports call them.
DERIVED_SECTIONS: tuple[tuple[str, str], ...] = (
    ("debate_bull", "Bull Researcher"),
    ("debate_bear", "Bear Researcher"),
    ("risk_aggressive", "Aggressive Analyst"),
    ("risk_conservative", "Conservative Analyst"),
    ("risk_neutral", "Neutral Analyst"),
)

# Every panel, in the order the pipeline produces them, which is the order the
# UI stacks them in regardless of which finishes first.
DISPLAY_ORDER: tuple[tuple[str, str], ...] = (
    REPORT_SECTIONS[:4]                       # the analysts
    + DERIVED_SECTIONS[:2]                    # the research debate
    + REPORT_SECTIONS[4:6]                    # research manager, trader
    + DERIVED_SECTIONS[2:]                    # the risk debate
    + REPORT_SECTIONS[6:]                     # the decision
)

_ANALYST_REPORT_KEY = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}


@dataclass
class RunRecord:
    """One analysis: what was asked for, what has arrived, and how it ended."""

    id: str
    ticker: str
    trade_date: str
    analysts: list[str]
    asset_type: str
    with_portfolio: bool
    settings: dict[str, Any]
    batch_id: str | None = None
    status: str = "queued"          # queued | running | done | failed | cancelled
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    rating: str | None = None
    needs_review: bool = False
    error: str | None = None
    report_path: str | None = None
    reports: dict[str, str] = field(default_factory=dict)
    agents_done: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    _subscribers: list[queue.Queue] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def summary(self) -> dict:
        """The record as the run list shows it: no transcript, no reports."""
        return {
            "id": self.id,
            "ticker": self.ticker,
            "trade_date": self.trade_date,
            "analysts": self.analysts,
            "asset_type": self.asset_type,
            "with_portfolio": self.with_portfolio,
            "batch_id": self.batch_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "rating": self.rating,
            "needs_review": self.needs_review,
            "error": self.error,
            "settings": self.settings,
        }

    def detail(self) -> dict:
        """Everything a reloaded page needs to render the run as it stands."""
        with self._lock:
            return {
                **self.summary(),
                "reports": dict(self.reports),
                "agents_done": list(self.agents_done),
                "messages": list(self.messages[-400:]),
                "stats": dict(self.stats),
                "report_path": self.report_path,
            }

    # --- event fan-out ---

    def emit(self, kind: str, **payload) -> None:
        """Record an event and hand it to every live subscriber."""
        event = {"seq": len(self.events), "kind": kind, "at": time.time(), **payload}
        with self._lock:
            self.events.append(event)
            if kind == "message":
                self.messages.append(payload)
            elif kind == "report":
                self.reports[payload["key"]] = payload["content"]
            elif kind == "stats":
                self.stats = payload.get("stats", {})
            elif kind == "agent" and payload["agent"] not in self.agents_done:
                self.agents_done.append(payload["agent"])
            subscribers = list(self._subscribers)
        for sink in subscribers:
            # A browser that stopped reading must not block the worker; its
            # queue fills, the event is dropped, and its reconnect replays from zero.
            with contextlib.suppress(queue.Full):
                sink.put_nowait(event)

    def subscribe(self) -> tuple[queue.Queue, list[dict]]:
        """A live queue plus everything that already happened, taken together.

        Both under the lock, so an event emitted between the replay and the
        subscription can be neither missed nor delivered twice.
        """
        sink: queue.Queue = queue.Queue(maxsize=2000)
        with self._lock:
            backlog = list(self.events)
            self._subscribers.append(sink)
        return sink, backlog

    def unsubscribe(self, sink: queue.Queue) -> None:
        with self._lock:
            if sink in self._subscribers:
                self._subscribers.remove(sink)

    def cancel(self) -> bool:
        """Ask the run to stop. A queued run stops now; a running one at its next step."""
        if self.status in ("done", "failed", "cancelled"):
            return False
        self._cancel.set()
        if self.status == "queued":
            self.status = "cancelled"
            self.finished_at = time.time()
            self.emit("status", status="cancelled")
        return True


class RunManager:
    """Owns the queue, the worker and every run this process has executed."""

    def __init__(self, config_factory=None, portfolio_loader=None, max_runs: int = 200):
        self._config_factory = config_factory or (lambda: DEFAULT_CONFIG.copy())
        self._portfolio_loader = portfolio_loader or (lambda: None)
        self._runs: dict[str, RunRecord] = {}
        self._order: list[str] = []
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._max_runs = max_runs
        self._worker = threading.Thread(target=self._work, name="tradingagents-ui", daemon=True)
        self._worker.start()

    # --- submission ---

    def submit(self, *, ticker: str, trade_date: str, analysts: list[str],
               settings: dict, with_portfolio: bool, batch_id: str | None = None) -> RunRecord:
        """Queue one analysis. Validates the ticker/analyst pairing before accepting it.

        The asset type is detected the way the CLI detects it, and analysts the
        asset does not support are dropped here rather than failing inside the
        graph: a crypto ticker has no SEC filings to analyze.
        """
        ticker = (ticker or "").strip().upper()
        if not ticker:
            raise ValueError("name a ticker to analyze")

        asset_type = detect_asset_type(ticker)
        known = {a.value: a for a in AnalystType}
        unknown = [a for a in analysts if a not in known]
        if unknown:
            raise ValueError(f"unknown analyst {', '.join(unknown)}")
        allowed = filter_analysts_for_asset_type([known[a] for a in analysts], asset_type)
        if not allowed:
            raise ValueError(f"no analyst selected is available for {asset_type.value}")

        record = RunRecord(
            id=uuid.uuid4().hex[:12],
            ticker=ticker,
            trade_date=trade_date,
            analysts=[a.value for a in allowed],
            asset_type=asset_type.value,
            with_portfolio=with_portfolio,
            settings=settings,
            batch_id=batch_id,
        )
        with self._lock:
            self._runs[record.id] = record
            self._order.append(record.id)
            self._evict_locked()
        record.emit("status", status="queued")
        self._queue.put(record.id)
        return record

    def _evict_locked(self) -> None:
        """Drop the oldest finished runs once the history exceeds its cap."""
        while len(self._order) > self._max_runs:
            for index, run_id in enumerate(self._order):
                if self._runs[run_id].status in ("done", "failed", "cancelled"):
                    self._order.pop(index)
                    self._runs.pop(run_id, None)
                    break
            else:
                return

    # --- reads ---

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[dict]:
        with self._lock:
            records = [self._runs[run_id] for run_id in self._order]
        return [r.summary() for r in reversed(records)]

    # --- the worker ---

    def _work(self) -> None:
        while True:
            run_id = self._queue.get()
            record = self.get(run_id)
            try:
                if record is None or record._cancel.is_set():
                    continue
                self._execute(record)
            except Exception:                        # never let the worker die
                logger.exception("run %s failed outside its own handler", run_id)
            finally:
                self._queue.task_done()

    def _execute(self, record: RunRecord) -> None:
        """Drive the graph for one run, mirroring what ``cli/run.py`` does.

        Same initial state (so the memory log is settled and past lessons are
        injected), same stream, same decision recording, same report tree. The
        only addition is turning each step into an event.
        """
        record.status = "running"
        record.started_at = time.time()
        record.emit("status", status="running")

        config = self._config_factory()
        config.update({k: v for k, v in record.settings.items() if v is not None})

        portfolio = self._portfolio_loader() if record.with_portfolio else None
        stats = StatsCallbackHandler()
        final_state: dict = {}

        try:
            graph = TradingAgentsGraph(
                record.analysts, config=config, debug=True, callbacks=[stats],
            )
            init_state = graph.create_run_state(
                record.ticker, record.trade_date, record.asset_type, portfolio,
            )
            args = graph.propagator.get_graph_args(callbacks=[stats])
            thread_id = graph.begin_checkpoint(
                record.ticker, record.trade_date, record.asset_type, portfolio,
            )
            if thread_id is not None:
                args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = thread_id
                record.emit("message", type="System", content=(
                    f"Resuming the saved run for {record.ticker}" if graph._resuming
                    else f"Starting fresh for {record.ticker}"
                ))

            seen_messages: set = set()
            last_stats = 0.0
            try:
                for messages, chunk in graph.stream_run(graph.checkpoint_input(init_state), **args):
                    if record._cancel.is_set():
                        raise _Cancelled()

                    for message in messages:
                        key = getattr(message, "id", None)
                        if key is not None:
                            if key in seen_messages:
                                continue
                            seen_messages.add(key)
                        kind, content = classify_message_type(message)
                        if content and content.strip():
                            record.emit("message", type=kind, content=content.strip()[:4000])
                        for call in getattr(message, "tool_calls", None) or []:
                            name = call["name"] if isinstance(call, dict) else call.name
                            record.emit("message", type="Tool", content=name)

                    if time.time() - last_stats > 1.0:
                        last_stats = time.time()
                        record.emit("stats", stats=stats.get_stats())

                    if chunk is None:
                        continue

                    final_state.update(chunk)
                    self._emit_progress(record, chunk)

                record.emit("stats", stats=stats.get_stats())
                graph.record_decision(record.ticker, record.trade_date, final_state)
                graph.clear_checkpoint_on_success(
                    record.ticker, record.trade_date, record.asset_type, portfolio,
                )
            finally:
                graph.end_checkpoint()

            rating = run_rating(final_state)
            record.rating = rating
            record.needs_review = is_review(rating)
            try:
                record.report_path = tilde(graph.save_reports(final_state, record.ticker))
            except Exception as exc:                  # a saved report is not the run
                logger.warning("could not save reports for %s: %s", record.ticker, exc)
                record.emit("message", type="System", content=f"Report not saved: {exc}")

            record.status = "done"
            record.finished_at = time.time()
            record.emit("status", status="done", rating=rating,
                        needs_review=record.needs_review, report_path=record.report_path)

        except _Cancelled:
            record.status = "cancelled"
            record.finished_at = time.time()
            record.emit("status", status="cancelled")
        except Exception as exc:
            logger.exception("run %s (%s) failed", record.id, record.ticker)
            record.status = "failed"
            record.error = f"{type(exc).__name__}: {exc}"
            record.finished_at = time.time()
            record.emit("status", status="failed", error=record.error)

    def _emit_progress(self, record: RunRecord, chunk: dict) -> None:
        """Turn a state chunk into report and agent-status events."""
        for key, _label in REPORT_SECTIONS:
            content = chunk.get(key)
            if content and record.reports.get(key) != content:
                record.emit("report", key=key, content=content)

        for analyst in record.analysts:
            if chunk.get(_ANALYST_REPORT_KEY[analyst]):
                record.emit("agent", agent=analyst, state="completed")

        debate = chunk.get("investment_debate_state") or {}
        for side, name in (("bull_history", "bull"), ("bear_history", "bear")):
            if (debate.get(side) or "").strip():
                record.emit("agent", agent=name, state="completed")
                record.emit("report", key=f"debate_{name}", content=debate[side])

        risk = chunk.get("risk_debate_state") or {}
        for side, name in (("aggressive_history", "aggressive"),
                           ("conservative_history", "conservative"),
                           ("neutral_history", "neutral")):
            if (risk.get(side) or "").strip():
                record.emit("agent", agent=name, state="completed")
                record.emit("report", key=f"risk_{name}", content=risk[side])


class _Cancelled(Exception):
    """A run the user stopped, so it is not reported as a failure."""


def available_analysts(ticker: str) -> list[str]:
    """Analyst keys the given ticker supports, in canonical order."""
    asset = detect_asset_type(ticker) if ticker else AssetType.STOCK
    return [a.value for a in filter_analysts_for_asset_type(list(AnalystType), asset)]
