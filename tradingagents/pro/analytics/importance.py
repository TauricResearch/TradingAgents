"""Permutation feature importance (track T3): model-agnostic and seeded.

Ranks features by how much a caller-supplied score drops when that feature's
column is randomly shuffled — the standard permutation-importance recipe. It's
model-agnostic (you pass the ``scorer``, which may wrap any fitted model or a
strategy objective), pure stdlib (no sklearn), and deterministic under a seed,
so it fits the lean-install + determinism invariants of the analytics layer.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

# scorer(feature_matrix, target) -> score; higher is better
Scorer = Callable[[Sequence[Sequence[float]], Sequence[float]], float]


@dataclass(frozen=True)
class FeatureImportance:
    feature: str
    importance: float  # mean score drop when this feature is permuted
    std: float         # std of the drop across repeats (stability of the estimate)

    def as_dict(self) -> dict:
        return asdict(self)


def permutation_importance(
    feature_matrix: Sequence[Sequence[float]],
    target: Sequence[float],
    scorer: Scorer,
    *,
    feature_names: Sequence[str] | None = None,
    n_repeats: int = 10,
    seed: int = 0,
) -> list[FeatureImportance]:
    """Importance of each feature = mean drop in ``scorer`` when that feature's
    column is shuffled (``n_repeats`` times), returned sorted most-important
    first. ``feature_matrix`` is rows=samples × cols=features. Deterministic:
    one ``random.Random(seed)`` drives all shuffles."""
    rows = [list(r) for r in feature_matrix]
    n_samples = len(rows)
    n_features = len(rows[0]) if rows else 0
    if n_samples < 2 or n_features == 0:
        return []
    names = list(feature_names) if feature_names is not None else [
        f"f{j}" for j in range(n_features)]
    if len(names) != n_features:
        raise ValueError("feature_names length must match the number of columns")

    rng = random.Random(seed)
    baseline = scorer(rows, target)
    out: list[FeatureImportance] = []
    for j in range(n_features):
        column = [row[j] for row in rows]
        drops: list[float] = []
        for _ in range(max(1, n_repeats)):
            shuffled = column[:]
            rng.shuffle(shuffled)
            permuted = [row[:] for row in rows]
            for i in range(n_samples):
                permuted[i][j] = shuffled[i]
            drops.append(baseline - scorer(permuted, target))
        out.append(FeatureImportance(
            feature=names[j],
            importance=statistics.mean(drops),
            std=statistics.pstdev(drops) if len(drops) > 1 else 0.0))
    out.sort(key=lambda r: r.importance, reverse=True)
    return out


def feature_importance_report(
    feature_matrix: Sequence[Sequence[float]],
    target: Sequence[float],
    scorer: Scorer,
    *,
    feature_names: Sequence[str] | None = None,
    n_repeats: int = 10,
    seed: int = 0,
) -> list[dict]:
    """``permutation_importance`` as a list of plain dicts (for artifacts/UI)."""
    return [fi.as_dict() for fi in permutation_importance(
        feature_matrix, target, scorer, feature_names=feature_names,
        n_repeats=n_repeats, seed=seed)]


def negative_mse_scorer(
    feature_matrix: Sequence[Sequence[float]], target: Sequence[float],
) -> float:
    """Default scorer: negative MSE of a closed-form single-feature-agnostic
    linear predictor — the standardized feature sum fit to the target by a
    single OLS slope/intercept. Pure stdlib; higher (less negative) is better.
    Handy when you just want to rank raw features against a target without
    bringing your own model."""
    n = len(target)
    if n < 2:
        return 0.0
    preds = [sum(row) for row in feature_matrix]  # unweighted feature sum
    mean_x = statistics.mean(preds)
    mean_y = statistics.mean(target)
    var_x = statistics.pvariance(preds)
    if var_x == 0:
        return -statistics.pvariance(target)
    cov = sum((preds[i] - mean_x) * (target[i] - mean_y) for i in range(n)) / n
    slope = cov / var_x
    intercept = mean_y - slope * mean_x
    mse = sum((target[i] - (slope * preds[i] + intercept)) ** 2 for i in range(n)) / n
    return -mse


__all__ = [
    "FeatureImportance",
    "feature_importance_report",
    "negative_mse_scorer",
    "permutation_importance",
]
