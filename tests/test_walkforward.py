"""Walk-forward fold boundaries and promotion-gate aggregation."""

import json
from argparse import Namespace

import pytest

from tradingagents import backtest
from tradingagents.walkforward import (
    WalkForwardFold,
    _backtest_command,
    build_folds,
    partition_holdout,
    prediction_horizon_sessions,
    summarize_folds,
)


@pytest.mark.unit
def test_backtest_child_command_never_contains_database_credentials(tmp_path):
    secret = "postgresql://user:password@database.invalid/research"
    args = Namespace(
        tickers="AAPL,MSFT",
        benchmark="SPY",
        analysts="market,news",
        db=secret,
        max_runs_per_fold=2,
        replicates=1,
        portfolio_mode="long-only",
        gross_limit=1.0,
        max_weight=0.25,
        cost_bps=5.0,
        slippage_bps=5.0,
        annual_borrow_bps=300.0,
        tail_sessions=1,
        holding_sessions=5,
        placebo_trials=10,
        identity_control="none",
        debug=False,
        global_topics_only=False,
    )
    fold = WalkForwardFold(1, "2026-01-01", "2026-01-10", "2026-01-16", "2026-01-20")

    command = _backtest_command(args, fold, tmp_path / "fold.jsonl")

    assert "--db" not in command
    assert secret not in command


@pytest.mark.unit
def test_portfolio_tail_purge_includes_entry_session():
    assert prediction_horizon_sessions(holding_sessions=2, tail_sessions=5) == 6
    assert prediction_horizon_sessions(holding_sessions=5, tail_sessions=1) == 5


@pytest.mark.unit
def test_folds_have_training_embargo_and_disjoint_evaluation_windows():
    sessions = [f"2026-01-{day:02d}" for day in range(1, 16)]
    folds = build_folds(
        sessions,
        train_sessions=4,
        evaluation_sessions=3,
        embargo_sessions=1,
    )
    assert [(fold.train_start, fold.train_end) for fold in folds] == [
        ("2026-01-01", "2026-01-04"),
        ("2026-01-04", "2026-01-07"),
        ("2026-01-07", "2026-01-10"),
    ]
    assert [(fold.evaluation_start, fold.evaluation_end) for fold in folds] == [
        ("2026-01-06", "2026-01-08"),
        ("2026-01-09", "2026-01-11"),
        ("2026-01-12", "2026-01-14"),
    ]


@pytest.mark.unit
def test_folds_reject_overlapping_evaluation_spans():
    with pytest.raises(ValueError, match="step_sessions"):
        build_folds(
            [f"2026-01-{day:02d}" for day in range(1, 15)],
            train_sessions=3,
            evaluation_sessions=4,
            step_sessions=2,
        )


@pytest.mark.unit
def test_folds_reject_embargo_shorter_than_outcome_horizon():
    with pytest.raises(ValueError, match="prediction_horizon"):
        build_folds(
            [f"2026-01-{day:02d}" for day in range(1, 15)],
            train_sessions=3,
            evaluation_sessions=4,
            embargo_sessions=2,
            prediction_horizon_sessions=5,
        )


@pytest.mark.unit
def test_locked_holdout_has_a_horizon_sized_purge_gap():
    sessions = [f"2026-01-{day:02d}" for day in range(1, 21)]

    research, purge, holdout = partition_holdout(
        sessions, holdout_sessions=5, purge_sessions=3
    )

    assert research[-1] == "2026-01-12"
    assert purge == ["2026-01-13", "2026-01-14", "2026-01-15"]
    assert holdout == [
        "2026-01-16", "2026-01-17", "2026-01-18", "2026-01-19", "2026-01-20"
    ]


@pytest.mark.unit
def test_summary_compounds_folds_and_applies_promotion_gates(tmp_path):
    folds = build_folds(
        [f"2026-01-{day:02d}" for day in range(1, 13)],
        train_sessions=3,
        evaluation_sessions=2,
        embargo_sessions=1,
    )
    metrics = [
        {"total_return": 0.10, "benchmark_return": 0.04,
         "excess_return": 0.06, "max_drawdown": -0.05},
        {"total_return": 0.02, "benchmark_return": 0.01,
         "excess_return": 0.01, "max_drawdown": -0.08},
        {"total_return": -0.01, "benchmark_return": -0.03,
         "excess_return": 0.02, "max_drawdown": -0.10},
        {"total_return": 0.03, "benchmark_return": 0.01,
         "excess_return": 0.02, "max_drawdown": -0.04},
    ]
    for fold, fold_metrics in zip(folds, metrics, strict=True):
        path = tmp_path / f"fold-{fold.number:03d}.portfolio.json"
        manifest = {"start": fold.evaluation_start, "end": fold.evaluation_end}
        path.write_text(
            json.dumps({
                "portfolio_fingerprint": backtest._fingerprint(manifest),
                "manifest": manifest,
                "result": {
                    "metrics": fold_metrics,
                    "equity": [{"nav": 1.0 + fold_metrics["total_return"]}],
                },
                "diagnostics": {
                    "cross_sectional_rank_ic": {"mean_rank_ic": 0.10},
                    "baselines": {
                        "equal_weight": {"observed_minus_baseline_return": 0.01}
                    },
                    "ticker_permutation_placebo": {"empirical_p_value": 0.05},
                    "beta_attribution": {"annualized_residual_alpha": 0.02},
                },
            }), encoding="utf-8"
        )

    summary = summarize_folds(folds, tmp_path, minimum_folds=3)

    assert summary["folds_completed"] == 4
    assert summary["compounded_total_return"] == pytest.approx(
        1.10 * 1.02 * 0.99 * 1.03 - 1
    )
    assert summary["worst_fold_drawdown"] == -0.10
    assert summary["promotion_ready"] is True


@pytest.mark.unit
def test_stale_fold_artifact_with_wrong_manifest_is_rejected(tmp_path):
    folds = build_folds(
        [f"2026-01-{day:02d}" for day in range(1, 10)],
        train_sessions=3,
        evaluation_sessions=2,
    )
    path = tmp_path / "fold-001.portfolio.json"
    path.write_text(json.dumps({
        "portfolio_fingerprint": "stale",
        "manifest": {"start": "1900-01-01", "end": "1900-01-02"},
        "result": {"metrics": {}},
    }), encoding="utf-8")

    summary = summarize_folds(folds, tmp_path)

    assert summary["folds_completed"] == 0
    assert summary["promotion_ready"] is False
