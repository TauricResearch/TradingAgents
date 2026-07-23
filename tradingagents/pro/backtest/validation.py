"""Overfitting-aware validation (roadmap P2 / architecture track T3).

The differentiator identified in the framework survey (docs/research/
05_gap_analysis.md): no surveyed backtester ships these guards, and our KB's
central lesson (docs/research/03_institutional_best_practices.md) is that
every blow-up was a validation/risk failure. These are pure functions —
deterministic, dependency-light (stdlib ``statistics.NormalDist`` only) — so
the optimizer (optimize.py) can report, for any selected result, the
probability it is spurious.

References (paraphrased, cited in docs/research/12_validation_methodology.md):
- Bailey & López de Prado, "The Deflated Sharpe Ratio" (2014) — PSR / DSR.
- Bailey, Borwein, López de Prado & Zhu, "The Probability of Backtest
  Overfitting" (2015) — CSCV / PBO.
"""

from __future__ import annotations

import math
import statistics
from itertools import combinations

_NORMAL = statistics.NormalDist()
_EULER_MASCHERONI = 0.5772156649015329


def _moments(returns: list[float]) -> tuple[float, float, float]:
    """(std, skewness, non-excess kurtosis) of a return series. Kurtosis is
    the raw fourth standardized moment (3.0 for a normal), matching the PSR
    formula's convention."""
    n = len(returns)
    if n < 2:
        return 0.0, 0.0, 3.0
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / n
    if var <= 0:
        return 0.0, 0.0, 3.0
    std = math.sqrt(var)
    skew = (sum((r - mean) ** 3 for r in returns) / n) / std**3
    kurt = (sum((r - mean) ** 4 for r in returns) / n) / std**4
    return std, skew, kurt


def probabilistic_sharpe_ratio(
    sharpe: float, benchmark: float, n_obs: int,
    skew: float = 0.0, kurtosis: float = 3.0,
) -> float:
    """P(true Sharpe > ``benchmark``) given an observed Sharpe over ``n_obs``
    periods, correcting for non-normal returns (Bailey & López de Prado). All
    Sharpes are in the SAME period units (don't mix annualized with per-bar).
    Returns a probability in [0, 1]; 0.5 means the observed equals the
    benchmark."""
    if n_obs < 2:
        return 0.5
    denom = math.sqrt(max(1e-12, 1.0 - skew * sharpe
                          + ((kurtosis - 1.0) / 4.0) * sharpe**2))
    z = (sharpe - benchmark) * math.sqrt(n_obs - 1) / denom
    return _NORMAL.cdf(z)


def expected_max_sharpe(sharpe_variance: float, n_trials: int) -> float:
    """Expected maximum Sharpe from ``n_trials`` independent trials under the
    null of zero true Sharpe — the benchmark a selected best must beat. Grows
    with both the spread of trial Sharpes and the number of trials (more
    searching → a higher bar). Zero for a single trial (no selection)."""
    if n_trials <= 1 or sharpe_variance <= 0:
        return 0.0
    std = math.sqrt(sharpe_variance)
    g = _EULER_MASCHERONI
    return std * ((1 - g) * _NORMAL.inv_cdf(1 - 1.0 / n_trials)
                  + g * _NORMAL.inv_cdf(1 - 1.0 / (n_trials * math.e)))


def deflated_sharpe_ratio(
    candidate_sharpe: float, trial_sharpes: list[float],
    n_obs: int, skew: float = 0.0, kurtosis: float = 3.0,
) -> float:
    """Probability the selected (best-of-N) Sharpe reflects real skill rather
    than selection luck. It is the PSR measured against the expected-max-Sharpe
    benchmark implied by the spread and count of the trials — so a great Sharpe
    found only after trying hundreds of configurations deflates toward 0.5 or
    below. ``candidate_sharpe`` and ``trial_sharpes`` share period units."""
    n_trials = len(trial_sharpes)
    variance = (statistics.pvariance(trial_sharpes) if n_trials > 1 else 0.0)
    benchmark = expected_max_sharpe(variance, n_trials)
    return probabilistic_sharpe_ratio(
        candidate_sharpe, benchmark, n_obs, skew, kurtosis)


def deflated_sharpe_from_returns(
    returns_by_trial: list[list[float]], best_index: int,
    periods_per_year: int = 1,
) -> float:
    """Convenience: compute per-trial Sharpes from return series, then the DSR
    of the ``best_index`` trial (skew/kurtosis from its own returns). Sharpes
    are left in per-period units (periods_per_year cancels in the ratio, so it
    is accepted only for signature symmetry with the caller)."""
    sharpes = [_sharpe(r) for r in returns_by_trial]
    std, skew, kurt = _moments(returns_by_trial[best_index])
    return deflated_sharpe_ratio(
        sharpes[best_index], sharpes, len(returns_by_trial[best_index]),
        skew, kurt)


def _sharpe(returns: list[float]) -> float:
    std, _, _ = _moments(returns)
    if std <= 0 or not returns:
        return 0.0
    return (sum(returns) / len(returns)) / std


def probability_of_backtest_overfitting(
    perf_matrix: list[list[float]], n_slices: int = 10,
) -> float:
    """PBO via combinatorially-symmetric cross-validation (CSCV). ``perf_matrix``
    is one row per configuration, each row that config's per-period performance
    (e.g. returns), all rows equal length.

    For every way to split the periods into in-sample / out-of-sample halves,
    take the config that ranked best in-sample and measure where it lands
    out-of-sample; PBO is the fraction of splits where that in-sample winner
    lands below the out-of-sample median. **PBO near 0.5 means the selection
    has no out-of-sample edge** — the "best" config is likely overfit.

    Needs >= 2 configs and an even ``n_slices`` >= 4 (clamped to the number of
    periods). Returns a probability in [0, 1]."""
    n_configs = len(perf_matrix)
    if n_configs < 2:
        return 0.0
    t = len(perf_matrix[0])
    s = min(n_slices, t)
    s -= s % 2  # even
    if s < 4:
        return 0.0
    bounds = [round(k * t / s) for k in range(s + 1)]
    slices = [list(range(bounds[k], bounds[k + 1])) for k in range(s)]

    def _score(cfg: int, slice_ids) -> float:
        idx = [i for k in slice_ids for i in slices[k]]
        return sum(perf_matrix[cfg][i] for i in idx) / max(1, len(idx))

    overfit = 0
    total = 0
    for is_ids in combinations(range(s), s // 2):
        oos_ids = [k for k in range(s) if k not in set(is_ids)]
        is_scores = [_score(c, is_ids) for c in range(n_configs)]
        oos_scores = [_score(c, oos_ids) for c in range(n_configs)]
        best = max(range(n_configs), key=lambda c: is_scores[c])
        # relative OOS rank of the in-sample winner (1.0 = best OOS)
        worse = sum(1 for c in range(n_configs) if oos_scores[c] < oos_scores[best])
        w = worse / (n_configs - 1)
        if w <= 0.5:  # in-sample winner is at/below the OOS median → overfit
            overfit += 1
        total += 1
    return overfit / total if total else 0.0


__all__ = [
    "deflated_sharpe_from_returns",
    "deflated_sharpe_ratio",
    "expected_max_sharpe",
    "probabilistic_sharpe_ratio",
    "probability_of_backtest_overfitting",
]
