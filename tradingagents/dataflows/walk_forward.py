"""Walk-forward validation (Phase 7, contract sections 9 and 11).

Historical out-of-sample validation without look-ahead: the timeline is cut
into folds so that every decision is made using only information available
*before* its analysis date, and scored only against prices that came *after*
it. The module is pure — it computes folds, gates and honest summaries from
inputs; it never fetches prices and never runs an LLM.

Honesty rules the contract demands, enforced here:

- A fold's training window ends strictly before its test window starts; a
  decision in the test window never sees a lesson resolved after its date
  (the memory log's ``as_of`` guard, #1251, is the enforcement point).
- An outcome that has not settled yet is *pending*, not a zero: pending
  cells are counted and excluded from averages, never folded in as 0%.
- Small samples are labelled: a rating with fewer than ``min_samples``
  settled cells reports ``insufficient`` instead of a hit rate that would
  be noise.
- Alpha is measured from the first close *after* the analysis date over a
  declared holding window, against a declared benchmark — and the summary
  says so, with the caveat that one model sampling per cell is indicative,
  not repeatable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# A settled cell with fewer settled observations than this is reported as
# insufficient rather than scored: a 1-of-2 hit rate is noise, not evidence.
DEFAULT_MIN_SAMPLES = 5


def _parse(date_str: str) -> date:
    parsed = datetime.strptime(str(date_str), "%Y-%m-%d").date()
    if parsed.strftime("%Y-%m-%d") != str(date_str):
        raise ValueError(f"dates must be YYYY-MM-DD, got {date_str!r}")
    return parsed


@dataclass(frozen=True)
class WalkForwardFold:
    """One out-of-sample fold: a train window and the test window after it.

    ``train_end`` is the last day whose *outcomes* may inform the test
    window's decisions; ``test_start``/``test_end`` bound the analysis dates
    being validated. The boundary is strict: ``train_end < test_start``, so
    no outcome from inside the test window can leak into its own decisions.
    """

    fold_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str

    def context_as_of(self) -> str:
        """The ``as_of`` the memory log must be filtered to in this fold.

        Lessons resolved after ``train_end`` did not exist when the test
        window's decisions were made (#1251).
        """
        return self.train_end

    def validate(self) -> None:
        if not (self.train_start < self.train_end < self.test_start
                <= self.test_end):
            raise ValueError(
                f"fold {self.fold_index} windows overlap or are unordered: "
                f"train {self.train_start}..{self.train_end} must end strictly "
                f"before test {self.test_start}..{self.test_end}"
            )


def make_walk_forward_folds(
    start_date: str,
    end_date: str,
    *,
    train_days: int,
    test_days: int,
    step_days: int | None = None,
) -> list[WalkForwardFold]:
    """Cut a historical range into non-leaking walk-forward folds.

    Folds advance by ``step_days`` (default: ``test_days``, so consecutive
    test windows tile the range without overlap). Each fold's train window
    is the ``train_days`` immediately before its test window. The last fold
    never extends past ``end_date``.
    """
    start, end = _parse(start_date), _parse(end_date)
    if train_days < 1 or test_days < 1:
        raise ValueError("train_days and test_days must be at least 1")
    step = step_days if step_days is not None else test_days
    if step < 1:
        raise ValueError("step_days must be at least 1")

    folds: list[WalkForwardFold] = []
    index = 0
    test_start = start
    while True:
        test_end = test_start + timedelta(days=test_days - 1)
        if test_start > end:
            break
        if test_end > end:
            test_end = end  # the last fold is truncated, not dropped
        train_end = test_start - timedelta(days=1)
        train_start = train_end - timedelta(days=train_days - 1)
        fold = WalkForwardFold(
            fold_index=index,
            train_start=f"{train_start:%Y-%m-%d}",
            train_end=f"{train_end:%Y-%m-%d}",
            test_start=f"{test_start:%Y-%m-%d}",
            test_end=f"{test_end:%Y-%m-%d}",
        )
        fold.validate()
        folds.append(fold)
        if test_end >= end:
            break
        test_start = test_start + timedelta(days=step)
        index += 1
    return folds


@dataclass(frozen=True)
class SettledCell:
    """One backtest cell that has an outcome, ready to score.

    ``analysis_date`` is when the decision was made; ``entry_date`` the
    first close after it (alpha is measured from there, never from a price
    the decision could not have seen); ``benchmark_return`` and
    ``holding_return`` cover the same window.
    """

    ticker: str
    analysis_date: str
    entry_date: str
    rating: str
    holding_return: float | None
    benchmark_return: float | None
    holding_days: int

    @property
    def alpha(self) -> float | None:
        """Return over the benchmark over the same window, or None if unsettled."""
        if self.holding_return is None or self.benchmark_return is None:
            return None
        return self.holding_return - self.benchmark_return

    @property
    def direction(self) -> int | None:
        """The direction the rating claimed: +1 long, -1 short, 0 none."""
        return {"Buy": 1, "Overweight": 1, "Hold": 0,
                "Underweight": -1, "Sell": -1}.get(self.rating)


@dataclass
class RatingScore:
    """One rating's out-of-sample record, honestly labelled."""

    rating: str
    count: int
    directional_calls: int          # cells whose rating claimed a direction
    hits: int                       # direction calls that matched alpha's sign
    mean_alpha: float | None
    insufficient: bool

    def render(self) -> str:
        if self.insufficient:
            return (f"- {self.rating}: n={self.count} — insufficient settled "
                    f"samples for a hit rate (min {DEFAULT_MIN_SAMPLES})")
        called = (f"called the direction {self.hits}/{self.directional_calls}"
                  if self.directional_calls else "no direction claimed")
        alpha = f"{self.mean_alpha:+.2%}" if self.mean_alpha is not None else "n/a"
        return f"- {self.rating}: n={self.count}, {called}, mean alpha {alpha}"


@dataclass
class WalkForwardSummary:
    """The honest aggregate: pending counted, small samples labelled."""

    folds: int
    cells_total: int
    cells_settled: int
    cells_pending: int
    by_rating: dict[str, RatingScore] = field(default_factory=dict)
    holding_window: str = ""
    benchmark: str = ""

    @property
    def all_scored(self) -> bool:
        return self.cells_pending == 0

    def render(self) -> str:
        lines = [
            f"Walk-forward: {self.folds} folds, {self.cells_total} cells "
            f"({self.cells_settled} settled, {self.cells_pending} pending)",
            f"Alpha measured from the first close after each analysis date "
            f"over {self.holding_window} vs {self.benchmark}.",
        ]
        for rating in sorted(self.by_rating):
            lines.append(self.by_rating[rating].render())
        lines += [
            "",
            "One model sampling per cell and non-archived text feeds make "
            "these figures indicative rather than repeatable. Pending cells "
            "are excluded from the averages, not counted as zero.",
        ]
        return "\n".join(lines)


def score_cells(
    cells: list[SettledCell],
    *,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> dict[str, RatingScore]:
    """Score settled cells per rating, labelling small samples insufficient.

    Pending cells never reach here (they have no outcome); a cell whose
    outcome is missing is excluded from its rating's mean, not counted as
    zero. Hold claims no direction, so nothing about alpha proves it right
    or wrong — its hit rate is reported as no direction claimed.
    """
    by_rating: dict[str, list[SettledCell]] = {}
    for cell in cells:
        by_rating.setdefault(cell.rating, []).append(cell)

    scores: dict[str, RatingScore] = {}
    for rating, rating_cells in sorted(by_rating.items()):
        alphas = [c.alpha for c in rating_cells if c.alpha is not None]
        directional = [c for c in rating_cells if c.direction]
        hits = sum(
            1 for c in directional
            if c.alpha is not None and (c.alpha > 0) - (c.alpha < 0) == c.direction
        )
        mean_alpha = (sum(alphas) / len(alphas)) if alphas else None
        scores[rating] = RatingScore(
            rating=rating,
            count=len(rating_cells),
            directional_calls=len(directional),
            hits=hits,
            mean_alpha=mean_alpha,
            insufficient=len(alphas) < min_samples,
        )
    return scores


def summarize_walk_forward(
    folds: list[WalkForwardFold],
    cells: list[SettledCell],
    *,
    cells_total: int | None = None,
    holding_window: str = "",
    benchmark: str = "",
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> WalkForwardSummary:
    """Aggregate folds and settled cells into the honest summary.

    ``cells_total`` is the number of cells the sweep ran (settled + pending);
    when omitted it is taken as the settled count, i.e. assuming nothing
    pending — pass the real number when you have it.
    """
    settled = len(cells)
    total = cells_total if cells_total is not None else settled
    return WalkForwardSummary(
        folds=len(folds),
        cells_total=total,
        cells_settled=settled,
        cells_pending=max(0, total - settled),
        by_rating=score_cells(cells, min_samples=min_samples),
        holding_window=holding_window,
        benchmark=benchmark,
    )
