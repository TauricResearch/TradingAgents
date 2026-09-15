"""Replay the agent graph over a date range and record every decision.

This is the expensive half of a backtest — one full graph run per decision
point — so the runner is built around not repeating work:

* Every decision is appended to a :class:`~tradingagents.backtest.store.DecisionStore`
  as soon as it is produced, and a resume skips points already stored. Losing a
  connection on day 40 of 60 costs the 41st decision, not the first 40.
* The store is keyed by a run signature covering the models, analyst selection
  and debate depth, so changing the config starts fresh instead of blending two
  experiments into one curve.

The graph is injected rather than constructed here, which keeps the whole
module testable without an API key: tests pass a stub whose ``propagate``
returns a canned rating.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from tradingagents.backtest.pricing import estimate_cost, load_price_table
from tradingagents.backtest.schedule import decision_dates
from tradingagents.backtest.store import DecisionRecord, DecisionStore
from tradingagents.dataflows.utils import safe_ticker_component

logger = logging.getLogger(__name__)


class GraphLike(Protocol):
    """The slice of ``TradingAgentsGraph`` the runner depends on."""

    def propagate(
        self, company_name: str, trade_date: str, asset_type: str = "stock"
    ) -> tuple[dict, str]:
        ...


# Builds a graph for one ticker. Takes the per-ticker config override (so each
# ticker can be given its own memory log) and the callback handlers to attach.
GraphFactory = Callable[[str, dict, list], GraphLike]


def run_signature(
    config: dict,
    selected_analysts: tuple[str, ...] | list[str],
    asset_type: str = "stock",
) -> str:
    """Identify the configuration a set of decisions was produced under.

    Broader than the graph's checkpoint signature, which only needs to describe
    graph *shape* within a single process. Decisions persist across runs and
    across config edits, so the models are included too: the same graph shape on
    a different model is a different experiment and must not share a key.
    """
    return "|".join([
        "analysts=" + ",".join(selected_analysts),
        f"debate={config.get('max_debate_rounds')}",
        f"risk={config.get('max_risk_discuss_rounds')}",
        f"asset={asset_type}",
        f"provider={config.get('llm_provider')}",
        f"deep={config.get('deep_think_llm')}",
        f"quick={config.get('quick_think_llm')}",
    ])


@dataclass
class BacktestSpec:
    """What to replay."""

    tickers: list[str]
    start: str
    end: str
    every_n_days: int = 5
    asset_type: str = "stock"
    selected_analysts: tuple[str, ...] = ("market", "social", "news", "fundamentals")
    max_workers: int = 1
    # Enforce the point-in-time rule during the run: any vendor request for a
    # date past the trade date aborts that decision. Off by default because the
    # guard is global process state and a violation costs a decision; on, it
    # makes the framework's look-ahead invariant testable end to end.
    strict_point_in_time: bool = False

    def __post_init__(self):
        if not self.tickers:
            raise ValueError("a backtest needs at least one ticker")
        if self.max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {self.max_workers}")
        # Normalise early so the store key, the memory-log filename and the
        # price lookup all agree on one spelling.
        self.tickers = [t.strip().upper() for t in self.tickers if t.strip()]
        if not self.tickers:
            raise ValueError("a backtest needs at least one ticker")
        # Reject a ticker that cannot be a path component here rather than
        # letting every date fail separately deep inside the run. Same guard the
        # results tree uses, applied before any work is scheduled.
        for ticker in self.tickers:
            safe_ticker_component(ticker)


@dataclass
class RunProgress:
    """One decision point's outcome, for progress reporting."""

    ticker: str
    date: str
    index: int
    total: int
    rating: str | None
    skipped: bool = False
    error: str | None = None


@dataclass
class RunSummary:
    """What a :meth:`BacktestRunner.run` actually did."""

    signature: str
    total_points: int
    produced: int = 0
    skipped: int = 0
    failed: int = 0
    wall_seconds: float = 0.0
    unpriced_models: set[str] = field(default_factory=set)


class BacktestRunner:
    """Drives the agent graph across a schedule, recording each decision."""

    def __init__(
        self,
        spec: BacktestSpec,
        store: DecisionStore,
        graph_factory: GraphFactory,
        config: dict,
        memory_dir: str | Path | None = None,
        on_progress: Callable[[RunProgress], None] | None = None,
    ):
        self.spec = spec
        self.store = store
        self.graph_factory = graph_factory
        self.config = config
        self.memory_dir = Path(memory_dir) if memory_dir else None
        self.on_progress = on_progress
        self.signature = run_signature(config, spec.selected_analysts, spec.asset_type)
        # Guards the shared RunSummary counters when tickers run concurrently.
        self._lock = threading.Lock()
        self._price_table = load_price_table(config)
        self._models = [
            m for m in (config.get("deep_think_llm"), config.get("quick_think_llm")) if m
        ]

    def _ticker_config(self, ticker: str) -> dict:
        """Config for one ticker's graph, with its own decision log.

        Two reasons this is not the user's live memory log. The log is rewritten
        whole by ``batch_update_with_outcomes`` (read, modify, atomic replace),
        so concurrent tickers sharing one file would clobber each other's
        reflections. And a backtest's reflections are simulated history — they
        belong to the backtest, not to the user's real trading record.
        """
        config = dict(self.config)
        if self.memory_dir is not None:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            config["memory_log_path"] = str(
                self.memory_dir / f"{safe_ticker_component(ticker)}.md"
            )
        return config

    def run(self) -> RunSummary:
        """Produce every missing decision in the schedule.

        Tickers run concurrently but each ticker's dates run in order, because
        the decision log is causal: a run on day N reflects on outcomes resolved
        from earlier runs of the same ticker. Shuffling a ticker's dates would
        feed it lessons out of sequence.
        """
        dates = decision_dates(self.spec.start, self.spec.end, self.spec.every_n_days)
        summary = RunSummary(
            signature=self.signature,
            total_points=len(dates) * len(self.spec.tickers),
        )
        if not dates:
            logger.warning(
                "Backtest schedule %s..%s contains no weekdays; nothing to run.",
                self.spec.start, self.spec.end,
            )
            return summary

        started = time.monotonic()
        workers = min(self.spec.max_workers, len(self.spec.tickers))
        if workers == 1:
            for ticker in self.spec.tickers:
                self._run_ticker(ticker, dates, summary)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(
                    lambda t: self._run_ticker(t, dates, summary), self.spec.tickers
                ))

        summary.wall_seconds = time.monotonic() - started
        return summary

    def _run_ticker(self, ticker: str, dates: list[str], summary: RunSummary) -> None:
        from tradingagents.stats import StatsCallbackHandler

        already = sum(1 for d in dates if self.store.has(ticker, d, self.signature))
        with self._lock:
            summary.skipped += already
        if already:
            logger.info(
                "Resuming %s: %d of %d decision points already stored.",
                ticker, already, len(dates),
            )

        # One graph and one usage handler per ticker, not per decision point:
        # constructing a graph builds two LLM clients and compiles the workflow,
        # which is pure overhead to repeat for every date. Per-decision usage
        # comes from diffing the handler around each call instead.
        handler = StatsCallbackHandler()
        cached: dict[str, GraphLike] = {}

        def graph_provider() -> GraphLike:
            if "graph" not in cached:
                cached["graph"] = self.graph_factory(
                    ticker, self._ticker_config(ticker), [handler]
                )
            return cached["graph"]

        for position, date in enumerate(dates, start=1):
            if self.store.has(ticker, date, self.signature):
                self._report(RunProgress(
                    ticker, date, position, len(dates), None, skipped=True
                ))
                continue

            record = self._run_point(ticker, date, graph_provider, handler)
            self.store.append(record)
            with self._lock:
                if record.ok:
                    summary.produced += 1
                else:
                    summary.failed += 1
                if record.cost_usd is None and record.tokens_in:
                    summary.unpriced_models.update(self._models)
            self._report(RunProgress(
                ticker, date, position, len(dates), record.rating, error=record.error,
            ))

    @contextmanager
    def _point_in_time_scope(self, date: str):
        """Hold this decision to its trade date, when the spec asks for it.

        A no-op context when ``strict_point_in_time`` is off, so the normal path
        carries no dispatch-hook overhead.
        """
        if not self.spec.strict_point_in_time:
            yield
            return
        from tradingagents.backtest.guard import point_in_time_guard

        with point_in_time_guard(date, strict=True):
            yield

    def _run_point(
        self,
        ticker: str,
        date: str,
        graph_provider: Callable[[], GraphLike],
        handler: Any,
    ) -> DecisionRecord:
        """Run one decision point, converting any failure into a stored record.

        A single bad date (a delisted symbol, a provider outage, a rate limit)
        must not abort a multi-hour backtest. The failure is recorded, counted
        in the scorecard's coverage section, and retried on the next resume.
        """
        started = time.monotonic()
        baseline = handler.get_stats()
        try:
            graph = graph_provider()
            with self._point_in_time_scope(date):
                _, signal = graph.propagate(ticker, date, self.spec.asset_type)
            usage = handler.delta_since(baseline)
            return DecisionRecord(
                ticker=ticker,
                date=date,
                signature=self.signature,
                rating=signal,
                decision=self._decision_text(graph),
                llm_calls=usage["llm_calls"],
                tool_calls=usage["tool_calls"],
                tokens_in=usage["tokens_in"],
                tokens_out=usage["tokens_out"],
                cost_usd=estimate_cost(
                    usage["tokens_in"], usage["tokens_out"],
                    self._models, self._price_table,
                ),
                wall_seconds=time.monotonic() - started,
            )
        except Exception as exc:  # noqa: BLE001 - one bad date must not end the run
            logger.warning("Decision failed for %s on %s: %s", ticker, date, exc)
            usage = handler.delta_since(baseline)
            return DecisionRecord(
                ticker=ticker,
                date=date,
                signature=self.signature,
                rating=None,
                llm_calls=usage["llm_calls"],
                tool_calls=usage["tool_calls"],
                tokens_in=usage["tokens_in"],
                tokens_out=usage["tokens_out"],
                wall_seconds=time.monotonic() - started,
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _decision_text(graph: Any) -> str:
        """The final decision prose, when the graph exposes its last state."""
        state = getattr(graph, "curr_state", None)
        if isinstance(state, dict):
            return str(state.get("final_trade_decision", ""))
        return ""

    def _report(self, progress: RunProgress) -> None:
        if self.on_progress is not None:
            self.on_progress(progress)


def default_graph_factory(
    selected_analysts: tuple[str, ...] = ("market", "social", "news", "fundamentals"),
) -> GraphFactory:
    """Build real ``TradingAgentsGraph`` instances for the runner.

    Imported lazily so the backtest package stays importable — and its tests
    stay runnable — without constructing an LLM client.
    """

    def factory(ticker: str, config: dict, callbacks: list) -> GraphLike:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        return TradingAgentsGraph(
            selected_analysts=selected_analysts,
            debug=False,
            config=config,
            callbacks=callbacks,
        )

    return factory
