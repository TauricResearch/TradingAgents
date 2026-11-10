"""Running one analysis for the web UI, off the request thread.

This mirrors ``cli.run.run_analysis`` step for step — same config assembly, same
graph, same live-state buffer, same checkpoint handling and same report writer —
but publishes the state as a snapshot the page polls, instead of drawing it into
a terminal with ``rich``. The CLI modules are imported, never modified.

Runs execute in a background thread with a lock around the snapshot, so a slow
model call never blocks a request and a poll always reads a consistent view.
"""

from __future__ import annotations

import datetime
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from cli.display import (
    ANALYST_ORDER,
    AnalystWallTimeTracker,
    MessageBuffer,
    classify_message_type,
    update_analyst_statuses,
    update_research_team_status,
)
from cli.models import AssetType
from cli.prompts import (
    detect_asset_type,
    parse_analysis_date,
    parse_analysts,
    parse_ticker,
)
from cli.run import _build_run_config, _run_directory
from cli.stats_handler import StatsCallbackHandler
from tradingagents.agents.rating import is_review, run_rating
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import build_analyst_execution_plan
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.portfolio import PortfolioContext
from webapp.rendering import render_markdown

logger = logging.getLogger(__name__)

# How many recent messages and tool calls a run keeps for the page. The graph
# can emit thousands over a long run; the page shows the tail, as the CLI does.
MESSAGE_HISTORY = 60
TOOL_HISTORY = 30

# The page polls about once a second; copying the live buffer more often than
# this would only churn, since no reader would see the intermediate snapshots.
PUBLISH_INTERVAL = 0.4


class RunRequestError(ValueError):
    """A request the run cannot start with; the message is shown to the user."""


@dataclass
class RunOptions:
    """One analysis, as asked for by the page."""

    ticker: str
    analysis_date: str
    analysts: str | list[str] | None = None
    asset_type: str | None = None
    research_depth: int = 3
    llm_provider: str | None = None
    backend_url: str | None = None
    quick_think_llm: str | None = None
    deep_think_llm: str | None = None
    output_language: str | None = None
    google_thinking_level: str | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    checkpoint: bool | None = None
    save: bool = True
    html: bool = True
    portfolio: dict | None = None

    def resolved(self) -> dict:
        """The request checked into the selections ``_build_run_config`` takes.

        Every check is the CLI's own (``parse_ticker``, ``parse_analysis_date``,
        ``parse_analysts``), so the page refuses exactly what a CLI run would.
        Their ``ValueError`` is re-raised as ``RunRequestError``: the same
        contract, but one type the API turns into a 422 with the reason.
        """
        try:
            ticker = parse_ticker(self.ticker)
            analysis_date = parse_analysis_date(self.analysis_date or today())
        except ValueError as exc:
            raise RunRequestError(str(exc)) from None

        if self.asset_type:
            try:
                asset_type = AssetType(str(self.asset_type).strip().lower())
            except ValueError:
                raise RunRequestError(
                    f"unknown asset type {self.asset_type!r}; use stock or crypto"
                ) from None
        else:
            asset_type = detect_asset_type(ticker)

        names = self.analysts
        if isinstance(names, (list, tuple)):
            names = ",".join(str(n) for n in names)
        if not names:
            raise RunRequestError("select at least one analyst")
        try:
            analysts = parse_analysts(names, asset_type)
        except ValueError as exc:
            raise RunRequestError(str(exc)) from None

        if self.research_depth not in (1, 3, 5):
            raise RunRequestError("research depth must be 1, 3 or 5")

        provider = (self.llm_provider or DEFAULT_CONFIG["llm_provider"]).strip().lower()
        backend_url = self.backend_url or DEFAULT_CONFIG["backend_url"]
        quick = self.quick_think_llm or DEFAULT_CONFIG["quick_think_llm"]
        deep = self.deep_think_llm or DEFAULT_CONFIG["deep_think_llm"]
        if not quick or not deep:
            raise RunRequestError("choose a quick and a deep thinking model")

        portfolio = None
        if self.portfolio:
            try:
                portfolio = PortfolioContext.model_validate(self.portfolio)
            except Exception as exc:  # pydantic's message says which field is wrong
                raise RunRequestError(f"portfolio is not usable: {exc}") from None

        return {
            "ticker": ticker,
            "asset_type": asset_type.value,
            "analysis_date": analysis_date,
            "analysts": analysts,
            "research_depth": self.research_depth,
            "llm_provider": provider,
            "backend_url": backend_url,
            "quick_think_llm": quick,
            "deep_think_llm": deep,
            "google_thinking_level": self.google_thinking_level,
            "openai_reasoning_effort": self.openai_reasoning_effort,
            "anthropic_effort": self.anthropic_effort,
            "output_language": self.output_language or DEFAULT_CONFIG["output_language"],
            "portfolio": portfolio,
            "checkpoint": self.checkpoint,
            "save": self.save,
            "html": self.html,
        }


@dataclass
class Run:
    """One analysis and everything the page needs to show about it."""

    id: str
    ticker: str
    analysis_date: str
    asset_type: str
    analysts: list[str]
    status: str = "running"
    phase: str = "Starting"
    error: str | None = None
    rating: str | None = None
    note: str | None = None
    report_dir: str | None = None
    report_html: str | None = None
    report_markdown: str | None = None

    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    published_at: float = 0.0

    messages: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    agent_status: dict[str, str] = field(default_factory=dict)
    report_sections: dict[str, str | None] = field(default_factory=dict)
    current_report: str | None = None
    stats: dict = field(default_factory=dict)
    wall_time_summary: str = ""

    cancel_requested: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict:
        """A consistent copy of the run, safe to serialise while it advances."""
        with self._lock:
            elapsed = None
            if self.started_at is not None:
                elapsed = round((self.finished_at or time.time()) - self.started_at, 1)
            done = sum(1 for s in self.agent_status.values() if s == "completed")
            reports_done = sum(
                1 for section, content in self.report_sections.items() if content
            )
            return {
                "id": self.id,
                "ticker": self.ticker,
                "analysis_date": self.analysis_date,
                "asset_type": self.asset_type,
                "analysts": list(self.analysts),
                "status": self.status,
                "phase": self.phase,
                "error": self.error,
                "rating": self.rating,
                "note": self.note,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "elapsed": elapsed,
                "messages": list(self.messages),
                "tool_calls": list(self.tool_calls),
                "agent_status": dict(self.agent_status),
                "report_sections": dict(self.report_sections),
                # The same sections as safe HTML, rendered once per text by
                # `webapp.rendering`; the page inserts them, so the report reads
                # as it does in the terminal and in the saved HTML page.
                "report_sections_html": {
                    section: render_markdown(
                        "\n".join(str(item) for item in content) if isinstance(content, list) else content
                    )
                    for section, content in self.report_sections.items()
                    if content
                },
                "current_report": self.current_report,
                "stats": dict(self.stats),
                "wall_time_summary": self.wall_time_summary,
                "progress": {
                    "agents_completed": done,
                    "agents_total": len(self.agent_status),
                    "reports_completed": reports_done,
                    "reports_total": len(self.report_sections),
                },
                "report_available": bool(self.report_html or self.report_markdown),
            }

    def finish(self, status: str, error: str | None = None) -> None:
        with self._lock:
            self.status = status
            self.error = error
            self.finished_at = time.time()
            self.phase = {
                "completed": "Completed",
                "failed": "Failed",
                "cancelled": "Cancelled",
            }.get(status, status)


class RunManager:
    """Every run this process has started, and the thread running each."""

    def __init__(self, history: int = 25):
        self._runs: dict[str, Run] = {}
        self._order: list[str] = []
        self._history = history
        self._lock = threading.Lock()

    # -- lookup ---------------------------------------------------------------

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[dict]:
        with self._lock:
            runs = [self._runs[run_id] for run_id in reversed(self._order) if run_id in self._runs]
        return [run.snapshot() for run in runs]

    # -- lifecycle ------------------------------------------------------------

    def start(self, options: RunOptions) -> Run:
        """Check the request, register the run and start it in its own thread."""
        selections = options.resolved()
        run_id = uuid.uuid4().hex[:12]
        run = Run(
            id=run_id,
            ticker=selections["ticker"],
            analysis_date=selections["analysis_date"],
            asset_type=selections["asset_type"],
            analysts=[analyst.value for analyst in selections["analysts"]],
        )
        with self._lock:
            self._runs[run_id] = run
            self._order.append(run_id)
            self._evict_locked()
        thread = threading.Thread(
            target=self._execute, args=(run, selections), name=f"run-{run_id}", daemon=True
        )
        thread.start()
        return run

    def cancel(self, run_id: str) -> bool:
        """Ask the run to stop after the step in flight; a model call is not preempted."""
        run = self.get(run_id)
        if run is None or run.status != "running":
            return False
        run.cancel_requested = True
        run.phase = "Stopping after the current step"
        return True

    def _evict_locked(self) -> None:
        while len(self._order) > self._history:
            oldest = self._order.pop(0)
            existing = self._runs.get(oldest)
            if existing is not None and existing.status != "running":
                self._runs.pop(oldest, None)

    # -- the run itself -------------------------------------------------------

    def _execute(self, run: Run, selections: dict) -> None:
        run.started_at = time.time()
        try:
            self._run_analysis(run, selections)
        except BaseException as exc:  # a run's failure is data in the page, not a crash
            logger.exception("Run %s failed", run.id)
            run.note = None
            run.finish("failed", f"{type(exc).__name__}: {exc}")
        else:
            run.finish("cancelled" if run.cancel_requested else "completed")

    def _run_analysis(self, run: Run, selections: dict) -> None:
        portfolio = selections.get("portfolio")
        config = _build_run_config(selections, selections.get("checkpoint"))

        config.update(usage_source="web", usage_run_id=run.id)
        stats_handler = StatsCallbackHandler()
        # The analyst selection in the run's own fixed order, as the CLI does it.
        chosen = {analyst.value for analyst in selections["analysts"]}
        selected_analyst_keys = [key for key in ANALYST_ORDER if key in chosen]
        plan = build_analyst_execution_plan(selected_analyst_keys)

        run.phase = "Preparing the agent graph"
        graph = TradingAgentsGraph(
            selected_analyst_keys, config=config, debug=False, callbacks=[stats_handler]
        )

        buffer = MessageBuffer()
        buffer.init_for_analysis(selected_analyst_keys)

        results_dir = _run_directory(config, selections["ticker"], selections["analysis_date"])
        results_dir.mkdir(parents=True, exist_ok=True)
        report_dir = results_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        log_file = results_dir / "message_tool.log"
        log_file.touch(exist_ok=True)

        # The CLI appends every message and tool call to a log file next to the
        # run; the page does the same, so a run leaves the same trace on disk.
        def log_line(line: str) -> None:
            with open(log_file, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")

        original_add_message = buffer.add_message
        original_add_tool_call = buffer.add_tool_call
        original_update_section = buffer.update_report_section

        def add_message(message_type, content):
            original_add_message(message_type, content)
            timestamp, recorded_type, recorded = buffer.messages[-1]
            log_line(f"{timestamp} [{recorded_type}] {recorded}".replace("\n", " "))

        def add_tool_call(tool_name, tool_args):
            original_add_tool_call(tool_name, tool_args)
            timestamp, recorded_name, recorded_args = buffer.tool_calls[-1]
            log_line(f"{timestamp} [Tool Call] {recorded_name}({_format_args(recorded_args)})")

        def update_section(section_name, content):
            original_update_section(section_name, content)
            written = buffer.report_sections.get(section_name)
            if not written:
                return
            text = "\n".join(str(item) for item in written) if isinstance(written, list) else written
            (report_dir / f"{section_name}.md").write_text(text, encoding="utf-8")

        buffer.add_message = add_message
        buffer.add_tool_call = add_tool_call
        buffer.update_report_section = update_section

        tracker = AnalystWallTimeTracker(plan)

        buffer.add_message("System", f"Selected ticker: {selections['ticker']}")
        if selections["asset_type"] != "stock":
            buffer.add_message("System", f"Detected asset type: {selections['asset_type']}")
        buffer.add_message("System", f"Analysis date: {selections['analysis_date']}")
        buffer.add_message(
            "System", f"Selected analysts: {', '.join(selections_analyst_names(selections))}"
        )

        for spec in plan.specs:
            buffer.update_agent_status(spec.agent_node, "in_progress")
            tracker.mark_started(spec.key)

        run.phase = "Analysts working"
        self._publish(run, buffer, stats_handler, tracker, force=True)

        init_state = graph.create_run_state(
            selections["ticker"],
            selections["analysis_date"],
            selections["asset_type"],
            portfolio,
        )
        args = graph.propagator.get_graph_args(callbacks=[stats_handler])

        checkpoint_tid = graph.begin_checkpoint(
            selections["ticker"],
            selections["analysis_date"],
            selections["asset_type"],
            portfolio,
        )
        if checkpoint_tid is not None:
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = checkpoint_tid
        resumed = getattr(graph, "_resuming", False)
        buffer.add_message(
            "System",
            f"{'Resuming the saved run' if resumed else 'Starting fresh'} for "
            f"{selections['ticker']} on {selections['analysis_date']}",
        )

        final_state: dict = {}
        trace: list[dict] = []
        try:
            for messages, chunk in graph.stream_run(graph.checkpoint_input(init_state), **args):
                if run.cancel_requested:
                    run.phase = "Stopped before the next step"
                    return

                for message in messages:
                    message_id = getattr(message, "id", None)
                    if message_id is not None:
                        if message_id in buffer._processed_message_ids:
                            continue
                        buffer._processed_message_ids.add(message_id)

                    message_type, content = classify_message_type(message)
                    if content and content.strip():
                        buffer.add_message(message_type, content)

                    if getattr(message, "tool_calls", None):
                        for tool_call in message.tool_calls:
                            if isinstance(tool_call, dict):
                                buffer.add_tool_call(tool_call["name"], tool_call["args"])
                            else:
                                buffer.add_tool_call(tool_call.name, tool_call.args)

                if chunk is None:
                    self._publish(run, buffer, stats_handler, tracker)
                    continue

                update_analyst_statuses(buffer, chunk, wall_time_tracker=tracker)
                self._apply_team_progress(buffer, chunk)
                self._publish(run, buffer, stats_handler, tracker, force=True)
                trace.append(chunk)

            for chunk in trace:
                final_state.update(chunk)

            run.phase = "Recording the decision"
            graph.record_decision(
                selections["ticker"], selections["analysis_date"], final_state,
                portfolio=portfolio,
            )
            graph.clear_checkpoint_on_success(
                selections["ticker"],
                selections["analysis_date"],
                selections["asset_type"],
                portfolio,
            )
        finally:
            graph.end_checkpoint()

        for agent in buffer.agent_status:
            buffer.update_agent_status(agent, "completed")
        for section in buffer.report_sections:
            if section in final_state:
                buffer.update_report_section(section, final_state[section])

        buffer.add_message("System", f"Completed analysis for {selections['analysis_date']}")
        buffer.add_message("System", tracker.format_summary())
        run.wall_time_summary = tracker.format_summary()
        run.rating = run_rating(final_state)
        if is_review(run.rating):
            run.note = (
                "No rating could be read from the final decision, so this run is "
                "recorded for review rather than as a position."
            )

        if selections.get("save", True):
            run.phase = "Saving the report"
            try:
                report_file = graph.save_reports(
                    final_state,
                    selections["ticker"],
                    html=bool(selections.get("html", True)),
                )
                run.report_dir = str(Path(report_file).resolve().parent)
                run.report_html = str(Path(report_file).resolve()) if selections.get("html", True) else None
                run.report_markdown = str(Path(report_file).resolve().with_suffix(".md"))
            except Exception as exc:  # a report that cannot be written is not a failed run
                logger.warning("Saving the report for run %s failed: %s", run.id, exc)
                run.note = (run.note + " " if run.note else "") + f"The report could not be saved: {exc}"

        run.phase = "Completed"
        self._publish(run, buffer, stats_handler, tracker, force=True)

    @staticmethod
    def _apply_team_progress(buffer: MessageBuffer, chunk: dict) -> None:
        """The status moves the CLI's stream loop makes for the fixed teams."""
        if chunk.get("investment_debate_state"):
            debate = chunk["investment_debate_state"]
            bull = (debate.get("bull_history") or "").strip()
            bear = (debate.get("bear_history") or "").strip()
            judge = (chunk.get("investment_plan") or "").strip()
            if bull or bear:
                update_research_team_status("in_progress")
            if bull:
                buffer.update_report_section("investment_plan", f"### Bull Researcher Analysis\n{bull}")
            if bear:
                buffer.update_report_section("investment_plan", f"### Bear Researcher Analysis\n{bear}")
            if judge:
                buffer.update_report_section("investment_plan", f"### Research Manager Decision\n{judge}")
                buffer.update_agent_status("Research Manager", "completed")
                buffer.update_agent_status("Trader", "in_progress")

        if chunk.get("trader_investment_plan"):
            buffer.update_report_section("trader_investment_plan", chunk["trader_investment_plan"])
            if buffer.agent_status.get("Trader") != "completed":
                buffer.update_agent_status("Trader", "completed")
                buffer.update_agent_status("Aggressive Analyst", "in_progress")

        if chunk.get("risk_debate_state"):
            risk = chunk["risk_debate_state"]
            aggressive = (risk.get("aggressive_history") or "").strip()
            conservative = (risk.get("conservative_history") or "").strip()
            neutral = (risk.get("neutral_history") or "").strip()
            judge = (chunk.get("final_trade_decision") or "").strip()
            if aggressive:
                buffer.update_agent_status("Aggressive Analyst", "in_progress")
                buffer.update_report_section(
                    "final_trade_decision", f"### Aggressive Analyst Analysis\n{aggressive}"
                )
            if conservative:
                buffer.update_agent_status("Conservative Analyst", "in_progress")
                buffer.update_report_section(
                    "final_trade_decision", f"### Conservative Analyst Analysis\n{conservative}"
                )
            if neutral:
                buffer.update_agent_status("Neutral Analyst", "in_progress")
                buffer.update_report_section(
                    "final_trade_decision", f"### Neutral Analyst Analysis\n{neutral}"
                )
            if judge and buffer.agent_status.get("Portfolio Manager") != "completed":
                buffer.update_agent_status("Portfolio Manager", "in_progress")
                buffer.update_report_section(
                    "final_trade_decision", f"### Portfolio Manager Decision\n{judge}"
                )
                for analyst in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"):
                    buffer.update_agent_status(analyst, "completed")
                buffer.update_agent_status("Portfolio Manager", "completed")

    @staticmethod
    def _publish(run: Run, buffer: MessageBuffer, stats_handler, tracker, force: bool = False) -> None:
        """Copy the live buffer into the run's snapshot for the page to poll.

        A run can emit many sub-steps between two polls, so the copy is throttled;
        a state transition passes ``force`` to publish at once.
        """
        now = time.time()
        if not force and now - run.published_at < PUBLISH_INTERVAL:
            return
        stats = stats_handler.get_stats()
        with run._lock:
            run.published_at = now
            run.messages = [
                {"time": timestamp, "type": message_type, "content": content}
                for timestamp, message_type, content in list(buffer.messages)[-MESSAGE_HISTORY:]
            ]
            run.tool_calls = [
                {"time": timestamp, "name": name, "args": args}
                for timestamp, name, args in list(buffer.tool_calls)[-TOOL_HISTORY:]
            ]
            run.agent_status = dict(buffer.agent_status)
            run.report_sections = dict(buffer.report_sections)
            run.current_report = buffer.current_report
            run.stats = stats
            if tracker is not None:
                run.wall_time_summary = tracker.format_summary()


def selections_analyst_names(selections: dict) -> list[str]:
    """Analyst labels for the log line: "sentiment" is what users select."""
    return ["sentiment" if a.value == "social" else a.value for a in selections["analysts"]]


def _format_args(tool_args) -> str:
    text = str(tool_args)
    return text if len(text) <= 200 else text[:197] + "..."


def today() -> str:
    """The analysis date the page offers by default."""
    return datetime.datetime.now().strftime("%Y-%m-%d")
