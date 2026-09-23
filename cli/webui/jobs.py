"""Background runs and on-disk history for the web UI.

Nothing here knows about HTTP. A run executes on a worker thread and writes
into a ``MessageBuffer`` under a lock; the page takes a snapshot under the same
lock on each refresh, so a long run never blocks the browser and a page reload
does not lose it.
"""

from __future__ import annotations

import json
import re
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cli.main import ANALYST_ORDER, MessageBuffer, process_chunk
from cli.stats_handler import StatsCallbackHandler
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.agents.utils.rating import is_review, parse_rating
from tradingagents.backtest import run_backtest, summarize
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.graph.analyst_execution import (
    AnalystWallTimeTracker,
    build_analyst_execution_plan,
    get_initial_analyst_node,
)
from tradingagents.reporting import write_report_tree

PENDING, RUNNING, DONE, FAILED, CANCELLED = "pending", "running", "done", "failed", "cancelled"

# Team layout of the pipeline, in the order the graph runs it.
TEAMS = {
    "Analyst Team": ["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst"],
    **MessageBuffer.FIXED_AGENTS,
}

SECTION_TITLES = {
    "market_report": "Market Analyst",
    "sentiment_report": "Sentiment Analyst",
    "news_report": "News Analyst",
    "fundamentals_report": "Fundamentals Analyst",
    "investment_plan": "Research Team",
    "trader_investment_plan": "Trader",
    "final_trade_decision": "Risk & Portfolio Management",
}


# The five section headings write_report_tree emits. Agent reports carry their
# own "## " headings, so only these may split a saved report.
_SECTION_RE = re.compile(r"^## ((?:I|II|III|IV|V)\. .+)$", re.MULTILINE)


class _Cancelled(Exception):
    pass


@dataclass
class AnalysisJob:
    """One single-ticker analysis running on its own thread."""

    ticker: str
    trade_date: str
    asset_type: str
    analysts: list[str]
    config: dict
    portfolio: object = None
    id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    status: str = PENDING
    error: str | None = None
    rating: str | None = None
    report_path: Path | None = None
    final_state: dict | None = None
    started: float = 0.0
    finished: float | None = None
    judgments: dict | None = None  # the Sentiment Analyst's Jev judgments, once made

    def __post_init__(self):
        self.analysts = [a for a in ANALYST_ORDER if a in set(self.analysts)]
        if not self.analysts:
            raise ValueError("Pick at least one analyst.")
        self.buffer = MessageBuffer(max_length=500)
        self.buffer.init_for_analysis(self.analysts)
        self.stats = StatsCallbackHandler()
        self.lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def label(self) -> str:
        return f"{self.ticker} · {self.trade_date}"

    @property
    def active(self) -> bool:
        return self.status in (PENDING, RUNNING)

    def start(self) -> AnalysisJob:
        self.started = time.time()
        self.status = RUNNING
        self._thread = threading.Thread(target=self._run, name=f"analysis-{self.id}", daemon=True)
        self._thread.start()
        return self

    def cancel(self) -> None:
        """Stop after the current graph step; a checkpointed run can resume later."""
        self._cancel.set()

    def elapsed(self) -> float:
        return (self.finished or time.time()) - self.started if self.started else 0.0

    def snapshot(self) -> dict:
        """A consistent copy of everything the page shows."""
        with self.lock:
            return {
                "status": self.status,
                "agent_status": dict(self.buffer.agent_status),
                "sections": dict(self.buffer.report_sections),
                "messages": list(self.buffer.messages),
                "tool_calls": list(self.buffer.tool_calls),
                "stats": self.stats.get_stats(),
                "elapsed": self.elapsed(),
                "rating": self.rating,
                "error": self.error,
                "report_path": self.report_path,
                "judgments": self.judgments,
            }

    def _log(self, text: str) -> None:
        with self.lock:
            self.buffer.add_message("System", text)

    def _run(self) -> None:
        # Imported here so a missing provider SDK surfaces as this run's error.
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph = None
        try:
            self._log(f"Analyzing {self.ticker} on {self.trade_date} with: {', '.join(self.analysts)}")
            graph = TradingAgentsGraph(
                self.analysts, config=self.config, debug=False, callbacks=[self.stats]
            )
            plan = build_analyst_execution_plan(self.analysts)
            tracker = AnalystWallTimeTracker(plan)
            with self.lock:
                self.buffer.update_agent_status(get_initial_analyst_node(plan), "in_progress")
            tracker.mark_started(self.analysts[0])

            init_state = graph.create_run_state(
                self.ticker, self.trade_date, self.asset_type, self.portfolio
            )
            args = graph.propagator.get_graph_args(callbacks=[self.stats])
            tid = graph.begin_checkpoint(self.ticker, self.trade_date, self.asset_type, self.portfolio)
            if tid is not None:
                args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid
                if getattr(graph, "_resuming", False):
                    self._log("Resuming the saved checkpoint for this ticker and date")

            final_state: dict = {}
            try:
                for chunk in graph.graph.stream(graph.checkpoint_input(init_state), **args):
                    if self._cancel.is_set():
                        raise _Cancelled
                    with self.lock:
                        process_chunk(self.buffer, chunk, wall_time_tracker=tracker)
                        if chunk.get("sentiment_judgments"):
                            self.judgments = chunk["sentiment_judgments"]
                    # Chunks are per-node deltas; merge them into the full state.
                    final_state.update(chunk)
                graph.record_decision(self.ticker, self.trade_date, final_state)
                graph.clear_checkpoint_on_success(
                    self.ticker, self.trade_date, self.asset_type, self.portfolio
                )
            finally:
                graph.end_checkpoint()

            rating = graph.process_signal(final_state.get("final_trade_decision", ""))
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = (Path(self.config["results_dir"]) / "reports"
                         / f"{safe_ticker_component(self.ticker)}_{stamp}")
            report_path = write_report_tree(final_state, self.ticker, save_path)

            with self.lock:
                for agent in self.buffer.agent_status:
                    self.buffer.update_agent_status(agent, "completed")
                for section in self.buffer.report_sections:
                    if final_state.get(section):
                        self.buffer.update_report_section(section, final_state[section])
                self.buffer.add_message("System", tracker.format_summary())
                if is_review(rating):
                    self.buffer.add_message(
                        "System", "The final decision has no tradeable rating (none could "
                        "be read, or the claim check sent it to review); it is logged for "
                        "review rather than as a position.")
                self.final_state = final_state
                self.rating = rating
                self.report_path = report_path
                self.status = DONE
        except _Cancelled:
            with self.lock:
                self.buffer.add_message("System", "Stopped by user")
                self.status = CANCELLED
        except Exception as exc:
            with self.lock:
                self.buffer.add_message("System", f"Failed: {exc}")
                self.error = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
                self.status = FAILED
        finally:
            self.finished = time.time()


@dataclass
class BacktestJob:
    """A grid backtest on its own thread; progress is read from its decision log."""

    tickers: list[str]
    dates: list[str]
    config: dict
    analysts: list[str]
    asset_type: str = "stock"
    portfolio: object = None
    run_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    status: str = PENDING
    error: str | None = None
    result: object = None
    started: float = 0.0
    finished: float | None = None
    initial_logged: int = 0

    def __post_init__(self):
        self.run_id = safe_ticker_component(self.run_id)
        self.current: tuple[str, str] | None = None  # (ticker, date) of the running cell
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def id(self) -> str:
        return f"backtest_{self.run_id}"

    @property
    def label(self) -> str:
        return f"Backtest {self.run_id} · {', '.join(self.tickers)}"

    @property
    def active(self) -> bool:
        return self.status in (PENDING, RUNNING)

    @property
    def total_cells(self) -> int:
        return len(self.tickers) * len(self.dates)

    @property
    def log_path(self) -> Path:
        return backtest_dir(self.config) / self.run_id / "trading_memory.md"

    def elapsed(self) -> float:
        return (self.finished or time.time()) - self.started if self.started else 0.0

    def cells_logged(self) -> int:
        return len(TradingMemoryLog({"memory_log_path": str(self.log_path)}).load_entries())

    def cancel(self) -> None:
        """Start no further cell; the running one finishes and is logged."""
        self._cancel.set()

    @property
    def stopping(self) -> bool:
        return self._cancel.is_set() and self.active

    def start(self) -> BacktestJob:
        self.started = time.time()
        # Cells a resumed sweep already had; the time-left estimate counts only new ones.
        self.initial_logged = self.cells_logged()
        self.status = RUNNING
        self._thread = threading.Thread(target=self._run, name=self.id, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        try:
            self.result = run_backtest(
                self.tickers, self.dates, self.config, asset_type=self.asset_type,
                portfolio=self.portfolio, selected_analysts=self.analysts, run_id=self.run_id,
                on_cell=self._on_cell, should_stop=self._cancel.is_set,
            )
            self.status = CANCELLED if self.result.stopped else DONE
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
            self.status = FAILED
        finally:
            self.current = None
            self.finished = time.time()

    def _on_cell(self, ticker: str, date: str) -> None:
        self.current = (ticker, date)


class JobRegistry:
    """Every run started from this UI server, newest first."""

    def __init__(self):
        self._jobs: dict[str, object] = {}
        self._lock = threading.Lock()

    def add(self, job):
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id):
        return self._jobs.get(job_id)

    def of_type(self, cls) -> list:
        with self._lock:
            jobs = [j for j in self._jobs.values() if isinstance(j, cls)]
        return sorted(jobs, key=lambda j: j.started, reverse=True)


# --- History on disk -------------------------------------------------------

@dataclass
class SavedReport:
    path: Path
    ticker: str
    trade_date: str | None
    modified: datetime
    kind: str  # "report" (complete_report.md) or "state" (full_states_log JSON)

    @property
    def judgments_path(self) -> Path | None:
        """The Sentiment Analyst's saved Jev judgments, when the run made them."""
        if self.kind != "report":
            return None
        path = self.path.parent / "1_analysts" / "sentiment_judgments.json"
        return path if path.exists() else None

    @property
    def label(self) -> str:
        when = self.trade_date or self.modified.strftime("%Y-%m-%d %H:%M")
        return f"{self.ticker} · {when}"


def backtest_dir(config: dict) -> Path:
    return Path(config["results_dir"]) / "backtest"


def list_saved_reports(results_dir) -> list[SavedReport]:
    """Report trees and state logs under ``results_dir``, newest first."""
    root = Path(results_dir)
    if not root.exists():
        return []
    found = []
    for path in root.rglob("complete_report.md"):
        ticker, trade_date = _report_header(path)
        found.append(SavedReport(path, ticker, trade_date, _mtime(path), "report"))
    for path in root.rglob("full_states_log_*.json"):
        # <results>/<TICKER>/TradingAgentsStrategy_logs/full_states_log_<date>.json
        found.append(SavedReport(path, path.parent.parent.name,
                                 path.stem.removeprefix("full_states_log_"), _mtime(path), "state"))
    return sorted(found, key=lambda r: r.modified, reverse=True)


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)


def _report_header(path: Path) -> tuple[str, str | None]:
    """(ticker, analysis date) from a complete report's header.

    Reports written before the header carried the date give None for it, and a
    report with no readable header falls back to its folder name for the ticker.
    """
    ticker, trade_date = path.parent.name.rsplit("_", 2)[0], None
    try:
        with path.open(encoding="utf-8") as f:
            head = [next(f, "") for _ in range(4)]
    except OSError:
        return ticker, None
    for line in head:
        if line.startswith("# Trading Analysis Report:"):
            ticker = line.split(":", 1)[1].strip()
        elif line.startswith("Analysis date:"):
            trade_date = line.split(":", 1)[1].strip() or None
    return ticker, trade_date


def load_report_sections(report: SavedReport) -> list[tuple[str, str]]:
    """(title, markdown) sections of a saved report, in pipeline order."""
    if report.kind == "report":
        text = report.path.read_text(encoding="utf-8")
        heads = list(_SECTION_RE.finditer(text))
        ends = [h.start() for h in heads[1:]] + [len(text)]
        return [(h.group(1).strip(), text[h.end():end].strip())
                for h, end in zip(heads, ends, strict=True)]
    state = json.loads(report.path.read_text(encoding="utf-8"))
    state.setdefault("trader_investment_plan", state.get("trader_investment_decision"))
    return state_sections(state)


def state_sections(state: dict) -> list[tuple[str, str]]:
    """Group a final state into the five report sections the CLI prints."""
    def join(parts):
        return "\n\n".join(f"### {name}\n{text}" for name, text in parts if text)

    debate = state.get("investment_debate_state") or {}
    risk = state.get("risk_debate_state") or {}
    sections = [
        ("I. Analyst Team Reports", join([
            ("Market Analyst", state.get("market_report")),
            ("Sentiment Analyst", state.get("sentiment_report")),
            ("News Analyst", state.get("news_report")),
            ("Fundamentals Analyst", state.get("fundamentals_report")),
        ])),
        ("II. Research Team Decision", join([
            ("Bull Researcher", debate.get("bull_history")),
            ("Bear Researcher", debate.get("bear_history")),
            ("Research Manager", debate.get("judge_decision")),
        ])),
        ("III. Trading Team Plan", join([("Trader", state.get("trader_investment_plan"))])),
        ("IV. Risk Management Team Decision", join([
            ("Aggressive Analyst", risk.get("aggressive_history")),
            ("Conservative Analyst", risk.get("conservative_history")),
            ("Neutral Analyst", risk.get("neutral_history")),
        ])),
        ("V. Portfolio Manager Decision", join([("Portfolio Manager", risk.get("judge_decision"))])),
    ]
    return [(title, body) for title, body in sections if body]


def report_rating(sections: list[tuple[str, str]]) -> str:
    """The Portfolio Manager's rating in a saved report, or REVIEW when unreadable."""
    body = next((b for t, b in sections if t.startswith("V.")), "")
    return parse_rating(body)


def load_judgments(report: SavedReport) -> dict | None:
    path = report.judgments_path
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_backtests(config: dict) -> list[Path]:
    """Backtest run directories that have a decision log, newest first."""
    root = backtest_dir(config)
    if not root.exists():
        return []
    runs = [p for p in root.iterdir() if (p / "trading_memory.md").exists()]
    return sorted(runs, key=lambda p: (p / "trading_memory.md").stat().st_mtime, reverse=True)


def load_decisions(log_path) -> list[dict]:
    """Rows of a decision log, with alpha and raw return as fractions."""
    rows = []
    for e in TradingMemoryLog({"memory_log_path": str(log_path)}).load_entries():
        rows.append({
            "date": e["date"],
            "ticker": e["ticker"],
            "rating": e["rating"],
            "status": "pending" if e["pending"] else "settled",
            "return": _pct(e.get("raw")),
            "alpha": _pct(e.get("alpha")),
            "holding": e.get("holding"),
            "decision": e.get("decision", ""),
            "reflection": e.get("reflection", ""),
        })
    return rows


def backtest_summary(log_path):
    return summarize(TradingMemoryLog({"memory_log_path": str(log_path)}))


def _pct(text) -> float | None:
    try:
        return float(str(text).strip().rstrip("%")) / 100
    except (TypeError, ValueError):
        return None
