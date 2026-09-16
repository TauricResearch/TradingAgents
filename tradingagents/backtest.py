"""Run the graph over a grid of tickers and dates, and score what came back.

One run yields one decision, so it cannot say whether the system decides well.
This runs the same machinery over many (ticker, date) cells and reads the
aggregate. The decision log is the results table: every run already records its
rating and later settles it with realized and alpha return against the
instrument's regional benchmark, so there is nothing to record separately.

Scope: this evaluates decision quality. It is not a portfolio simulator, and
must not grow one. Turning a rating into a filled order needs a quantity, a fill
price and a cash ledger, none of which the system has; inventing them here would
put an execution model behind an evaluation tool. Cells are therefore
independent, and a portfolio, when given, is the same standing book for every
cell rather than a position carried forward.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.dataflows.utils import get_current_date, safe_ticker_component
from tradingagents.graph.trading_graph import TradingAgentsGraph

logger = logging.getLogger(__name__)


def iter_grid(start_date: str, end_date: str, every_n_days: int = 1) -> list[str]:
    """Analysis dates from ``start_date``, never past today.

    A future date has no outcome to settle against, and the graph rejects one, so
    the grid stops at the present rather than producing cells that cannot score.
    """
    start, end = _canonical(start_date), _canonical(end_date)
    if every_n_days < 1:
        raise ValueError("every_n_days must be at least 1")

    last = min(end, datetime.strptime(get_current_date(), "%Y-%m-%d"))
    dates, cursor = [], start
    while cursor <= last:
        dates.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=every_n_days)
    return dates


def _canonical(date: str) -> datetime:
    """Parse a grid bound, rejecting anything the run date would also reject."""
    try:
        parsed = datetime.strptime(str(date), "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"grid dates must be in YYYY-MM-DD format, got {date!r}") from exc
    if parsed.strftime("%Y-%m-%d") != str(date):
        raise ValueError(f"grid dates must be in YYYY-MM-DD format, got {date!r}")
    return parsed


def _alpha(entry: dict) -> float | None:
    """Alpha return of a settled entry, or None when it has not settled.

    The log stores it as a percentage rounded to one decimal, so aggregates here
    are accurate to 0.1 of a percentage point, not to the raw quote.
    """
    text = (entry.get("alpha") or "").strip().rstrip("%")
    try:
        return float(text) / 100
    except ValueError:
        return None


@dataclass
class BacktestResult:
    run_id: str
    log_path: Path
    cells_run: int = 0
    skipped: int = 0
    failures: list[tuple[str, str, str]] = field(default_factory=list)
    settlement_failures: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class RatingScore:
    count: int
    hit_rate: float
    mean_alpha: float


@dataclass
class BacktestSummary:
    resolved: int
    pending: int
    by_rating: dict[str, RatingScore]

    def render(self) -> str:
        lines = [f"Resolved cells: {self.resolved} · pending: {self.pending}"]
        for rating, score in self.by_rating.items():
            lines.append(
                f"- {rating}: n={score.count}, beat the benchmark "
                f"{score.hit_rate:.0%}, mean alpha {score.mean_alpha:+.2%}"
            )
        lines += [
            "",
            "Pending cells are not scored above; re-run to settle them.",
            "One model sampling per cell, and text feeds are not archived, so "
            "these figures are indicative rather than repeatable.",
        ]
        return "\n".join(lines)


def run_backtest(
    tickers: list[str],
    dates: list[str],
    config: dict,
    asset_type: str = "stock",
    portfolio=None,
    selected_analysts=("market", "social", "news", "fundamentals"),
    run_id: str | None = None,
) -> BacktestResult:
    """Analyze every ticker on every date, into a decision log of this run's own.

    The live log stays untouched: a sweep would otherwise flood the context that
    real runs read back. Cells already in this run's log are skipped, so an
    interrupted sweep resumes by being run again.
    """
    # run_id becomes a path segment, so it is validated like a ticker: an
    # absolute or dotted value would otherwise place the run outside results_dir.
    run_id = safe_ticker_component(run_id or datetime.now().strftime("%Y%m%d_%H%M%S"))
    run_dir = Path(config["results_dir"]) / "backtest" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_config = {**config, "results_dir": str(run_dir),
                  "memory_log_path": str(run_dir / "trading_memory.md")}

    graph = TradingAgentsGraph(selected_analysts, config=run_config)
    result = BacktestResult(run_id=run_id, log_path=Path(run_config["memory_log_path"]))
    done = {(e["ticker"], e["date"]) for e in graph.memory_log.load_entries()}

    for ticker in tickers:
        for date in dates:
            if (ticker, date) in done:
                result.skipped += 1
                continue
            try:
                graph.propagate(ticker, date, asset_type, portfolio=portfolio)
                result.cells_run += 1
            except Exception as exc:  # one unreachable vendor must not end the sweep
                logger.warning("Backtest cell %s %s failed: %s", ticker, date, exc)
                result.failures.append((ticker, date, str(exc)))

    # Settlement runs at the start of the next run for a ticker, so each ticker's
    # last cell would stay pending without this pass.
    for ticker in tickers:
        try:
            graph.settle_pending(ticker)
        except Exception as exc:  # reflection calls an LLM; one failure is not the sweep's
            logger.warning("Settling %s failed: %s", ticker, exc)
            result.settlement_failures.append((ticker, str(exc)))
    return result


def summarize(memory_log: TradingMemoryLog) -> BacktestSummary:
    """Score the settled decisions in a log, by rating."""
    entries = memory_log.load_entries()
    resolved = [(e, _alpha(e)) for e in entries if not e["pending"]]
    resolved = [(e, a) for e, a in resolved if a is not None]
    by_rating: dict[str, RatingScore] = {}
    for rating in dict.fromkeys(e["rating"] for e, _ in resolved):
        alphas = [a for e, a in resolved if e["rating"] == rating]
        by_rating[rating] = RatingScore(
            count=len(alphas),
            hit_rate=sum(a > 0 for a in alphas) / len(alphas),
            mean_alpha=sum(alphas) / len(alphas),
        )
    return BacktestSummary(resolved=len(resolved), pending=len(entries) - len(resolved),
                           by_rating=by_rating)
