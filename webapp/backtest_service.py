"""Running one backtest sweep for the web UI, off the request thread.

This wraps ``tradingagents.backtest.run_backtest`` — the same grid, the same
per-cell graph and settlement the CLI's ``backtest`` command runs — and
publishes progress as a snapshot the page polls. The sweep writes its own
memory log under ``results_dir/backtest/<run_id>/``, so the live log a real run
reads back is never flooded by a sweep.

One sweep at a time: the cells share one graph and one log, and two sweeps
running at once would double the model spend for no extra information. A
second request is refused until the first finishes or is cancelled.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from tradingagents.backtest import BacktestResult, iter_grid, run_backtest, summarize

# How many recent cell events a sweep keeps for the page. A long sweep can run
# hundreds of cells; the page shows the tail.
CELL_HISTORY = 40


class BacktestRequestError(ValueError):
    """A request the sweep cannot start with; the message is shown to the user."""


@dataclass
class BacktestOptions:
    """One sweep, as asked for by the page."""

    tickers: list[str]
    start_date: str
    end_date: str
    every_n_days: int = 7
    analysts: list[str] | None = None
    asset_type: str = "stock"
    portfolio: dict | None = None

    def resolved(self) -> dict:
        """The request checked into what ``run_backtest`` takes.

        The grid is built here, so a bad range is refused before any model is
        called and the page can show how many cells it asked for.
        """
        tickers = [t.strip() for t in self.tickers if t and t.strip()]
        if not tickers:
            raise BacktestRequestError("give at least one ticker, comma-separated")
        try:
            dates = iter_grid(self.start_date, self.end_date, self.every_n_days)
        except ValueError as exc:
            raise BacktestRequestError(str(exc)) from None
        if not dates:
            raise BacktestRequestError(
                "the grid is empty: the start date is after today, so no cell has an outcome to settle against"
            )
        asset_type = (self.asset_type or "stock").strip().lower()
        if asset_type not in ("stock", "crypto"):
            raise BacktestRequestError(f"unknown asset type {self.asset_type!r}; use stock or crypto")
        analysts = [a.strip().lower() for a in (self.analysts or []) if a and a.strip()]
        return {
            "tickers": tickers,
            "dates": dates,
            "every_n_days": self.every_n_days,
            "analysts": analysts or None,
            "asset_type": asset_type,
            "portfolio": self.portfolio,
        }


@dataclass
class BacktestRun:
    """One sweep and everything the page needs to show about it."""

    id: str
    tickers: list[str]
    dates: list[str]
    asset_type: str
    analysts: list[str]
    status: str = "running"
    phase: str = "Starting"
    error: str | None = None
    note: str | None = None
    cells_run: int = 0
    skipped: int = 0
    cells_total: int = 0
    failures: list[dict] = field(default_factory=list)
    settlement_failures: list[dict] = field(default_factory=list)
    summary: dict | None = None
    log_path: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    cancel_requested: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict:
        """A consistent copy of the sweep, safe to serialise while it advances."""
        with self._lock:
            return {
                "id": self.id,
                "tickers": list(self.tickers),
                "dates": list(self.dates),
                "asset_type": self.asset_type,
                "analysts": list(self.analysts),
                "status": self.status,
                "phase": self.phase,
                "error": self.error,
                "note": self.note,
                "cells_run": self.cells_run,
                "skipped": self.skipped,
                "cells_total": self.cells_total,
                "failures": list(self.failures),
                "settlement_failures": list(self.settlement_failures),
                "summary": dict(self.summary) if self.summary else None,
                "log_path": self.log_path,
                "created_at": self.created_at,
                "finished_at": self.finished_at,
            }

    def finish(self, status: str, error: str | None = None, error_note: str | None = None,
               phase: str | None = None) -> None:
        with self._lock:
            self.status = status
            self.error = error
            self.note = error_note
            self.finished_at = time.time()
            self.phase = phase or {
                "completed": "Completed",
                "failed": "Failed",
                "cancelled": "Cancelled",
            }.get(status, status)


class BacktestManager:
    """The sweeps this process has started, and the thread running each."""

    def __init__(self, history: int = 10):
        self._runs: dict[str, BacktestRun] = {}
        self._order: list[str] = []
        self._history = history
        self._lock = threading.Lock()
        self._active: str | None = None

    def get(self, run_id: str) -> BacktestRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> list[dict]:
        with self._lock:
            runs = [self._runs[run_id] for run_id in reversed(self._order) if run_id in self._runs]
        return [run.snapshot() for run in runs]

    def start(self, options: BacktestOptions, config: dict) -> BacktestRun:
        """Check the request, register the sweep and start it in its own thread.

        One sweep at a time: a second while one runs is refused, so the page
        cannot silently double the model spend.
        """
        selections = options.resolved()
        with self._lock:
            active = self._runs.get(self._active) if self._active else None
            if active is not None and active.status == "running":
                raise BacktestRequestError("a backtest is already running; wait for it or cancel it")
            run_id = time.strftime("web_%Y%m%d_%H%M%S")
            run = BacktestRun(
                id=run_id,
                tickers=selections["tickers"],
                dates=selections["dates"],
                asset_type=selections["asset_type"],
                analysts=selections["analysts"] or [],
            )
            run.cells_total = len(selections["tickers"]) * len(selections["dates"])
            self._runs[run_id] = run
            self._order.append(run_id)
            self._active = run_id
            self._evict_locked()
        thread = threading.Thread(
            target=self._execute, args=(run, selections, config), name=f"backtest-{run_id}", daemon=True
        )
        thread.start()
        return run

    def cancel(self, run_id: str) -> bool:
        """Ask the sweep to stop after the cell in flight; a cell is not preempted."""
        run = self.get(run_id)
        if run is None or run.status != "running":
            return False
        run.cancel_requested = True
        run.phase = "Stopping after the current cell"
        return True

    def _evict_locked(self) -> None:
        while len(self._order) > self._history:
            oldest = self._order.pop(0)
            existing = self._runs.get(oldest)
            if existing is not None and existing.status != "running":
                self._runs.pop(oldest, None)

    def _execute(self, run: BacktestRun, selections: dict, config: dict) -> None:
        def progress(done: int, total: int, ticker: str, date: str) -> None:
            if run.cancel_requested:
                raise _Cancelled()
            with run._lock:
                run.phase = f"Cell {done}/{total}: {ticker} on {date}"
                run.cells_run = done - 1

        try:
            result: BacktestResult = run_backtest(
                selections["tickers"],
                selections["dates"],
                config,
                asset_type=selections["asset_type"],
                portfolio=selections["portfolio"],
                run_id=run.id,
                progress=progress,
            )
        except _Cancelled:
            run.finish("cancelled", phase="Cancelled after the cell in flight")
        except BaseException as exc:  # a sweep's failure is data in the page, not a crash
            run.finish("failed", error=f"{type(exc).__name__}: {exc}")
        else:
            with run._lock:
                run.cells_run = result.cells_run
                run.skipped = result.skipped
                run.failures = [
                    {"ticker": ticker, "date": date, "reason": reason}
                    for ticker, date, reason in result.failures
                ]
                run.settlement_failures = [
                    {"ticker": ticker, "reason": reason}
                    for ticker, reason in result.settlement_failures
                ]
                run.log_path = str(result.log_path)
                run.phase = "Scoring the settled decisions"
            try:
                summary = summarize(result)
            except Exception as exc:  # a log that cannot be scored is not a failed sweep
                run.finish("completed", error_note=f"The sweep finished but could not be scored: {exc}")
            else:
                with run._lock:
                    run.summary = {
                        "resolved": summary.resolved,
                        "pending": summary.pending,
                        "unscored": summary.unscored,
                        "holding": summary.holding,
                        "by_rating": [
                            {
                                "rating": rating,
                                "count": score.count,
                                "hit_rate": score.hit_rate,
                                "mean_alpha": score.mean_alpha,
                            }
                            for rating, score in summary.by_rating.items()
                        ],
                    }
                run.finish("completed")
        finally:
            with self._lock:
                if self._active == run.id:
                    self._active = None


class _Cancelled(Exception):
    """Raised inside ``run_backtest``'s progress hook to stop the sweep."""
