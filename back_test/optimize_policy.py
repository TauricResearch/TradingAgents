"""Offline policy-parameter optimization for cached strategy/features.

This module intentionally does not call any LLM. It replays already-generated
strategy JSONs while Optuna searches execution-policy parameters, then evaluates
the selected parameters with walk-forward validation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[1]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

import pandas as pd

from back_test.engine import BacktestEngine, PROJECT_ROOT
from back_test.metrics import summarize


OPTIMIZATION_DIR = PROJECT_ROOT / "back_test" / "results" / "optimization"


@dataclass(frozen=True)
class Fold:
    index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str


def suggest_policy_params(trial) -> dict[str, Any]:
    """Map Optuna trials to the searchable execution-policy parameter space."""
    return {
        "max_trade_risk_pct": trial.suggest_float("max_trade_risk_pct", 0.008, 0.030, step=0.002),
        "max_single_add_pct": trial.suggest_float("max_single_add_pct", 3.0, 12.0, step=1.0),
        "max_position_after_add_pct": trial.suggest_float("max_position_after_add_pct", 0.35, 0.85, step=0.05),
        "max_adds_per_trade": trial.suggest_int("max_adds_per_trade", 0, 4),
        "min_days_between_adds": trial.suggest_int("min_days_between_adds", 1, 5),
        "max_entry_gap_above_plan_pct": trial.suggest_float("max_entry_gap_above_plan_pct", 0.000, 0.025, step=0.0025),
        "max_add_gap_above_plan_pct": trial.suggest_float("max_add_gap_above_plan_pct", 0.000, 0.015, step=0.0025),
        "obvious_bull_max_entry_gap_pct": trial.suggest_float("obvious_bull_max_entry_gap_pct", 0.005, 0.030, step=0.0025),
        "obvious_bull_max_add_gap_pct": trial.suggest_float("obvious_bull_max_add_gap_pct", 0.000, 0.010, step=0.0025),
        "entry_signal_ttl_trading_days": trial.suggest_int("entry_signal_ttl_trading_days", 1, 4),
        "add_signal_ttl_trading_days": trial.suggest_int("add_signal_ttl_trading_days", 1, 3),
        "block_shrinking_volume_adds": trial.suggest_categorical("block_shrinking_volume_adds", [True, False]),
        "shrinking_volume_close_hold_days": trial.suggest_int("shrinking_volume_close_hold_days", 1, 4),
        "add_key_level_tolerance_pct": trial.suggest_float("add_key_level_tolerance_pct", 0.000, 0.015, step=0.0025),
    }


def default_policy_params() -> dict[str, Any]:
    """Current hand-tuned defaults used as a stable baseline."""
    return {
        "max_trade_risk_pct": 0.020,
        "max_single_add_pct": 8.0,
        "max_position_after_add_pct": 0.60,
        "max_adds_per_trade": 2,
        "min_days_between_adds": 2,
        "max_entry_gap_above_plan_pct": 0.010,
        "max_add_gap_above_plan_pct": 0.008,
        "obvious_bull_max_entry_gap_pct": 0.015,
        "obvious_bull_max_add_gap_pct": 0.005,
        "entry_signal_ttl_trading_days": 2,
        "add_signal_ttl_trading_days": 1,
        "block_shrinking_volume_adds": True,
        "shrinking_volume_close_hold_days": 2,
        "add_key_level_tolerance_pct": 0.005,
    }


def _replace_nonfinite(value):
    if isinstance(value, dict):
        return {k: _replace_nonfinite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_nonfinite(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return 0.0
    return value


def score_metrics(metrics: dict[str, Any], report: Optional[dict[str, Any]] = None) -> float:
    """Single objective for Optuna: reward return quality and penalize fragility."""
    report = report or {}
    total = float(metrics.get("total_return") or 0.0)
    sharpe = float(metrics.get("sharpe_ratio") or 0.0)
    max_dd = abs(float(metrics.get("max_drawdown") or 0.0))
    n_trades = int(metrics.get("n_trades") or 0)
    risk_rejects = int(report.get("buy_rejected_risk_budget") or 0)
    gap_rejects = int(report.get("gap_buy_rejected") or 0)
    ttl_expired = int(report.get("signal_ttl_expired") or 0)

    trade_penalty = 0.02 if n_trades == 0 else 0.0
    operational_penalty = 0.001 * risk_rejects + 0.0002 * (gap_rejects + ttl_expired)
    return total + 0.05 * sharpe - 1.5 * max_dd - trade_penalty - operational_penalty


def run_backtest_metrics(
    ticker: str,
    start: str,
    end: str,
    params: dict[str, Any],
    *,
    initial_capital: float,
    strategies_dir: Optional[Path] = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    engine = BacktestEngine(
        ticker=ticker,
        start_date=start,
        end_date=end,
        initial_capital=initial_capital,
        strategies_dir=strategies_dir,
        **params,
    )
    result = engine.run()
    metrics = summarize(result.equity_curve["Equity"], result.trades)
    return metrics, result.report or {}, result.trades


def optimize_train_window(
    ticker: str,
    train_start: str,
    train_end: str,
    *,
    n_trials: int,
    seed: int,
    initial_capital: float,
    strategies_dir: Optional[Path] = None,
    score_fn: Callable[[dict[str, Any], dict[str, Any]], float] = score_metrics,
) -> tuple[dict[str, Any], float, list[dict[str, Any]]]:
    try:
        import optuna
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Optuna is not installed. Install project dependencies or run: pip install optuna"
        ) from exc

    def objective(trial) -> float:
        params = suggest_policy_params(trial)
        metrics, report, _trades = run_backtest_metrics(
            ticker,
            train_start,
            train_end,
            params,
            initial_capital=initial_capital,
            strategies_dir=strategies_dir,
        )
        score = score_fn(metrics, report)
        trial.set_user_attr("metrics", _replace_nonfinite(metrics))
        trial.set_user_attr("report", _replace_nonfinite(report))
        return score

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    trials = [
        {
            "number": trial.number,
            "value": trial.value,
            "params": trial.params,
            "metrics": trial.user_attrs.get("metrics", {}),
        }
        for trial in study.trials
    ]
    return dict(study.best_params), float(study.best_value), trials


def build_walk_forward_folds(
    trading_days: pd.Series,
    *,
    train_days: int,
    test_days: int,
    step_days: Optional[int] = None,
) -> list[Fold]:
    days = pd.Series(pd.to_datetime(trading_days).drop_duplicates()).sort_values().reset_index(drop=True)
    step = step_days or test_days
    if train_days <= 1 or test_days <= 0 or step <= 0:
        raise ValueError("train_days must be > 1 and test_days/step_days must be positive")

    folds: list[Fold] = []
    start_idx = 0
    fold_index = 0
    while start_idx + train_days + test_days <= len(days):
        train = days.iloc[start_idx:start_idx + train_days]
        test = days.iloc[start_idx + train_days:start_idx + train_days + test_days]
        folds.append(
            Fold(
                index=fold_index,
                train_start=train.iloc[0].strftime("%Y-%m-%d"),
                train_end=train.iloc[-1].strftime("%Y-%m-%d"),
                test_start=test.iloc[0].strftime("%Y-%m-%d"),
                test_end=test.iloc[-1].strftime("%Y-%m-%d"),
            )
        )
        fold_index += 1
        start_idx += step
    return folds


def _load_trading_days(ticker: str, start: str, end: str, initial_capital: float) -> pd.Series:
    engine = BacktestEngine(ticker, start, end, initial_capital=initial_capital)
    prices = engine.load_prices()
    if prices.empty:
        raise ValueError(f"No price data found for {ticker} between {start} and {end}")
    return prices["Date"]


def walk_forward_optimize(
    ticker: str,
    start: str,
    end: str,
    *,
    n_trials: int,
    train_days: int,
    test_days: int,
    step_days: Optional[int],
    seed: int,
    initial_capital: float,
    strategies_dir: Optional[Path] = None,
) -> dict[str, Any]:
    trading_days = _load_trading_days(ticker, start, end, initial_capital)
    folds = build_walk_forward_folds(
        trading_days,
        train_days=train_days,
        test_days=test_days,
        step_days=step_days,
    )
    if not folds:
        raise ValueError(
            f"Not enough trading days for train_days={train_days}, test_days={test_days}"
        )

    fold_results = []
    test_scores = []
    for fold in folds:
        best_params, best_train_score, trials = optimize_train_window(
            ticker,
            fold.train_start,
            fold.train_end,
            n_trials=n_trials,
            seed=seed + fold.index,
            initial_capital=initial_capital,
            strategies_dir=strategies_dir,
        )
        train_metrics, train_report, _ = run_backtest_metrics(
            ticker,
            fold.train_start,
            fold.train_end,
            best_params,
            initial_capital=initial_capital,
            strategies_dir=strategies_dir,
        )
        test_metrics, test_report, _ = run_backtest_metrics(
            ticker,
            fold.test_start,
            fold.test_end,
            best_params,
            initial_capital=initial_capital,
            strategies_dir=strategies_dir,
        )
        baseline_test_metrics, baseline_test_report, _ = run_backtest_metrics(
            ticker,
            fold.test_start,
            fold.test_end,
            default_policy_params(),
            initial_capital=initial_capital,
            strategies_dir=strategies_dir,
        )
        test_score = score_metrics(test_metrics, test_report)
        test_scores.append(test_score)
        fold_results.append({
            "fold": fold.__dict__,
            "best_params": best_params,
            "best_train_score": best_train_score,
            "train_metrics": train_metrics,
            "train_report": train_report,
            "test_score": test_score,
            "test_metrics": test_metrics,
            "test_report": test_report,
            "baseline_test_score": score_metrics(baseline_test_metrics, baseline_test_report),
            "baseline_test_metrics": baseline_test_metrics,
            "n_trials": n_trials,
            "trials": trials,
        })

    mean_test_score = sum(test_scores) / len(test_scores)
    return {
        "schema_version": "policy_optimization_v1",
        "optimizer": "optuna_tpe",
        "ticker": ticker,
        "start": start,
        "end": end,
        "initial_capital": initial_capital,
        "n_trials": n_trials,
        "train_days": train_days,
        "test_days": test_days,
        "step_days": step_days or test_days,
        "seed": seed,
        "search_space": {
            "source": "back_test.optimize_policy.suggest_policy_params",
            "default_params": default_policy_params(),
        },
        "summary": {
            "n_folds": len(fold_results),
            "mean_test_score": mean_test_score,
            "best_fold_index": max(
                range(len(fold_results)),
                key=lambda i: fold_results[i]["test_score"],
            ),
        },
        "folds": _replace_nonfinite(fold_results),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Optimize backtest execution-policy parameters with Optuna TPE and walk-forward validation."
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--n-trials", type=int, default=50)
    parser.add_argument("--train-days", type=int, default=120)
    parser.add_argument("--test-days", type=int, default=20)
    parser.add_argument("--step-days", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--strategies-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = walk_forward_optimize(
        args.ticker.upper(),
        args.start,
        args.end,
        n_trials=args.n_trials,
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
        seed=args.seed,
        initial_capital=args.initial_capital,
        strategies_dir=args.strategies_dir,
    )
    OPTIMIZATION_DIR.mkdir(parents=True, exist_ok=True)
    out_path = args.output
    if out_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = OPTIMIZATION_DIR / (
            f"{args.ticker.upper()}_{args.start}_{args.end}_optuna_tpe_{stamp}.json"
        )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(_replace_nonfinite(result), f, indent=2)

    print(f"Optimization written to: {out_path}")
    print(f"Folds: {result['summary']['n_folds']}")
    print(f"Mean test score: {result['summary']['mean_test_score']:.6f}")
    best = result["folds"][result["summary"]["best_fold_index"]]
    print(f"Best fold: {best['fold']['index']} test_score={best['test_score']:.6f}")
    print("Best-fold params:")
    for key, value in best["best_params"].items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
