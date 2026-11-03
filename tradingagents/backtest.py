"""Run the graph over a grid of tickers and dates, and score what came back.

One run yields one decision, so it cannot say whether the system decides well.
This runs the same machinery over many (ticker, date) cells and reads the
aggregate. The memory log is the results table: every run already records its
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

import itertools
import logging
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from tradingagents.agents.rating import RATING_REVIEW
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.memory import TradingMemoryLog

logger = logging.getLogger(__name__)


def iter_grid(start_date: str, end_date: str, every_n_days: int = 1) -> list[str]:
    """Analysis dates from ``start_date``, never past today.

    A future date has no outcome to settle against, and the graph rejects one, so
    the grid stops at the present rather than producing cells that cannot score.
    """
    start, end = _canonical(start_date), _canonical(end_date)
    if every_n_days < 1:
        raise ValueError("every_n_days must be at least 1")
    if end < start:
        raise ValueError(f"the grid ends before it starts: {end_date} is before {start_date}")

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


# What each rating claims will happen, so an outcome can be scored against it.
# Hold claims no direction, so nothing about alpha proves it right or wrong.
_DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}


@dataclass
class RatingScore:
    count: int
    hit_rate: float | None
    mean_alpha: float


@dataclass
class ShuffleResult:
    """Outcome of the rating-shuffle significance test for a backtest grid.

    ``observed`` is the mean of ``direction(rating) * alpha`` over directional
    cells. The null reassigns the ratings actually given within each analysis
    date across that date's tickers, so a market-wide move on one date cannot
    pass for skill; ``p_value`` uses the ``(1 + count) / (1 + n)`` form so it
    never claims exactly zero on a finite number of shuffles.
    """

    cells: int
    observed: float
    null_median: float
    null_p95: float
    p_value: float
    shuffles: int
    shuffled_dates: int
    scope: str

    def render(self) -> str:
        return (f"Rating-shuffle test: {self.cells} directional cells, "
                f"observed {self.observed:+.2%} per cell; shuffled ratings "
                f"median {self.null_median:+.2%}, 95th pct {self.null_p95:+.2%}; "
                f"p = {self.p_value:.3f} ({self.shuffles} shuffles, {self.scope})")


def rating_shuffle_test(
    cells: Iterable[tuple[str, str, float | None]],
    shuffles: int = 2000,
    seed: int = 0,
) -> ShuffleResult | None:
    """Test whether a grid's ratings beat randomly assigned ratings.

    ``cells`` are ``(date, rating, alpha)`` triples. Ratings outside
    ``_DIRECTION`` carry no claim and are ignored; Hold cells stay in the
    shuffle pool (a shuffled Hold claims no direction) but never count as
    directional cells. Returns None when no directional cell is scored.
    """
    if shuffles < 1:
        raise ValueError("shuffles must be at least 1")
    by_date: dict[str, list[tuple[str, float]]] = {}
    for date, rating, alpha in cells:
        if rating not in _DIRECTION or alpha is None:
            continue
        by_date.setdefault(str(date), []).append((rating, alpha))
    pairs = [pair for group in by_date.values() for pair in group]
    directional = sum(1 for rating, _ in pairs if _DIRECTION[rating])
    if not directional:
        return None

    def _stat(assigned: list[tuple[str, float]]) -> float:
        scored = [_DIRECTION[rating] * alpha for rating, alpha in assigned
                  if _DIRECTION[rating]]
        return sum(scored) / len(scored) if scored else 0.0

    observed = _stat(pairs)
    # A date with a single cell cannot be shuffled, so it only constrains the
    # null when at least two dates can be; otherwise shuffle across all cells.
    shuffled_dates = sum(1 for group in by_date.values() if len(group) >= 2)
    groups = list(by_date.values()) if shuffled_dates >= 2 else [pairs]
    scope = "within date" if shuffled_dates >= 2 else "across all cells"
    rng = random.Random(seed)
    nulls = []
    for _ in range(shuffles):
        shuffled: list[tuple[str, float]] = []
        for group in groups:
            ratings = [rating for rating, _ in group]
            rng.shuffle(ratings)
            shuffled.extend(zip(ratings, (alpha for _, alpha in group), strict=True))
        nulls.append(_stat(shuffled))
    nulls.sort()
    at_least = sum(1 for value in nulls if value >= observed)
    return ShuffleResult(
        cells=directional,
        observed=observed,
        null_median=nulls[shuffles // 2],
        null_p95=nulls[int(0.95 * shuffles)],
        p_value=(1 + at_least) / (1 + shuffles),
        shuffles=shuffles,
        shuffled_dates=shuffled_dates,
        scope=scope,
    )


@dataclass
class BacktestSummary:
    resolved: int
    pending: int
    by_rating: dict[str, RatingScore]
    unscored: int = 0
    holding: str = ""
    shuffle: ShuffleResult | None = None

    def render(self) -> str:
        lines = [f"Resolved cells: {self.resolved} · pending: {self.pending}"
                 + (f" · unscored: {self.unscored}" if self.unscored else "")]
        for rating, score in self.by_rating.items():
            called = (f"called the direction {score.hit_rate:.0%}"
                      if score.hit_rate is not None else "no direction claimed")
            lines.append(
                f"- {rating}: n={score.count}, {called}, "
                f"mean alpha {score.mean_alpha:+.2%} vs the benchmark"
            )
        lines.append("")
        if self.shuffle is not None:
            lines.append(self.shuffle.render())
        lines.append("")
        if self.pending:
            lines.append("Pending cells are not scored above; re-run to settle them.")
        lines.append(
            f"Alpha is measured over {self.holding} from the first close after each analysis date. "
            "One model sampling per cell, and text feeds are not archived, so "
            "these figures are indicative rather than repeatable."
        )
        return "\n".join(lines)


def _new_run(runs: Path) -> str:
    """A new run's id, stamped now, and its directory, claimed so no other sweep shares it."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    runs.mkdir(parents=True, exist_ok=True)
    for n in itertools.count(1):
        run_id = stamp if n == 1 else f"{stamp}_{n}"
        try:
            (runs / run_id).mkdir()
            return run_id
        except FileExistsError:
            continue


def run_backtest(
    tickers: list[str],
    dates: list[str],
    config: dict,
    asset_type: str = "stock",
    portfolio=None,
    selected_analysts=("market", "social", "news", "fundamentals"),
    run_id: str | None = None,
    progress: Callable[[int, int, str, str], None] | None = None,
) -> BacktestResult:
    """Analyze every ticker on every date, into a memory log of this run's own.

    The live log stays untouched: a sweep would otherwise flood the context that
    real runs read back. Cells already in this run's log are skipped, so an
    interrupted sweep resumes by being run again. ``progress(done, total,
    ticker, date)`` is called before each cell that runs.
    """
    runs = Path(config["results_dir"]) / "backtest"
    if run_id:
        # run_id becomes a path segment, so it is validated like a ticker: an
        # absolute or dotted value would otherwise place the run outside results_dir.
        run_id = safe_ticker_component(run_id)
        (runs / run_id).mkdir(parents=True, exist_ok=True)
    else:
        run_id = _new_run(runs)
    run_dir = runs / run_id
    run_config = {**config, "results_dir": str(run_dir),
                  "memory_log_path": str(run_dir / "trading_memory.md")}

    graph = TradingAgentsGraph(selected_analysts, config=run_config)
    result = BacktestResult(run_id=run_id, log_path=Path(run_config["memory_log_path"]))
    done = {(e["ticker"], e["date"]) for e in graph.memory_log.load_entries()}

    # A ticker or date given twice is one cell, run and settled once.
    tickers, dates = list(dict.fromkeys(tickers)), list(dict.fromkeys(dates))
    cells = [(ticker, date) for ticker in tickers for date in dates]
    todo = [cell for cell in cells if cell not in done]
    result.skipped = len(cells) - len(todo)
    for index, (ticker, date) in enumerate(todo, 1):
        if progress:
            progress(index, len(todo), ticker, date)
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
            settlement = graph.settle_pending(ticker)
            result.settlement_failures.extend(
                (failed_ticker, f"{date}: {reason}")
                for failed_ticker, date, reason in settlement.failed
            )
        except Exception as exc:  # reflection calls an LLM; one failure is not the sweep's
            logger.warning("Settling %s failed: %s", ticker, exc)
            result.settlement_failures.append((ticker, str(exc)))
    return result


def summarize(source: BacktestResult | str | Path) -> BacktestSummary:
    """Score the settled decisions of a backtest, or of a memory log at a path, by rating."""
    if isinstance(source, BacktestResult):
        path = source.log_path      # a run whose cells all failed wrote no log: nothing to score
    elif Path(source).is_file():
        path = Path(source)
    else:
        raise FileNotFoundError(f"no memory log at {source}")
    entries = TradingMemoryLog({"memory_log_path": str(path)}).load_entries()
    # A decision with no readable rating has no direction, so it can neither
    # count for nor against the system; it is reported as unscored instead.
    resolved = [(e, _alpha(e)) for e in entries
                if not e["pending"] and e["rating"] != RATING_REVIEW]
    resolved = [(e, a) for e, a in resolved if a is not None]
    by_rating: dict[str, RatingScore] = {}
    for rating in dict.fromkeys(e["rating"] for e, _ in resolved):
        alphas = [a for e, a in resolved if e["rating"] == rating]
        direction = _DIRECTION.get(rating, 0)
        by_rating[rating] = RatingScore(
            count=len(alphas),
            hit_rate=(sum(a * direction > 0 for a in alphas) / len(alphas)) if direction else None,
            mean_alpha=sum(alphas) / len(alphas),
        )
    unscored = sum(1 for e in entries if e["rating"] == RATING_REVIEW)
    # Report the window the outcomes were actually measured over, from the log.
    windows = {f"{e['holding'][:-1]} trading days" for e, _ in resolved
               if (e.get("holding") or "").endswith("d")}
    return BacktestSummary(resolved=len(resolved),
                           pending=len(entries) - len(resolved) - unscored,
                           by_rating=by_rating, unscored=unscored,
                           holding=", ".join(sorted(windows)) or "the configured window",
                           shuffle=rating_shuffle_test(
                               (e["date"], e["rating"], a) for e, a in resolved))
