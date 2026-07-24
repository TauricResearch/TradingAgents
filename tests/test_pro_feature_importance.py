"""Permutation feature importance (track T3): a feature carrying the signal
must rank above noise, and the estimate is deterministic under a seed."""

import random

from tradingagents.pro.analytics import (
    feature_importance_report,
    negative_mse_scorer,
    permutation_importance,
)


def _dataset(n=200, seed=0):
    """Feature 0 = the target + small noise (informative); features 1 and 2 are
    pure noise. Target is feature 0's signal."""
    rng = random.Random(seed)
    rows, target = [], []
    for _ in range(n):
        signal = rng.uniform(-1, 1)
        rows.append([
            signal + rng.gauss(0, 0.05),  # informative
            rng.uniform(-1, 1),           # noise
            rng.uniform(-1, 1),           # noise
        ])
        target.append(signal)
    return rows, target


def test_informative_feature_ranks_first():
    rows, target = _dataset()
    ranked = permutation_importance(
        rows, target, negative_mse_scorer,
        feature_names=["signal", "noise_a", "noise_b"], seed=1)
    assert ranked[0].feature == "signal"
    assert ranked[0].importance > ranked[1].importance
    # noise features carry ~no importance (permuting them barely moves the score)
    assert ranked[0].importance > 0


def test_deterministic_under_seed():
    rows, target = _dataset()
    a = permutation_importance(rows, target, negative_mse_scorer, seed=7)
    b = permutation_importance(rows, target, negative_mse_scorer, seed=7)
    assert [(r.feature, r.importance, r.std) for r in a] == \
           [(r.feature, r.importance, r.std) for r in b]


def test_report_is_sorted_dicts():
    rows, target = _dataset()
    report = feature_importance_report(
        rows, target, negative_mse_scorer,
        feature_names=["signal", "noise_a", "noise_b"], seed=1)
    assert isinstance(report, list) and isinstance(report[0], dict)
    imps = [r["importance"] for r in report]
    assert imps == sorted(imps, reverse=True)


def test_empty_or_degenerate_returns_empty():
    assert permutation_importance([], [], negative_mse_scorer) == []
    assert permutation_importance([[1.0]], [0.5], negative_mse_scorer) == []
