"""Non-overlapping walk-forward orchestration for portfolio experiments.

The runner reserves a trailing training window for each fold, applies an
embargo, and scores only the subsequent evaluation window.  TradingAgents does
not currently fit parameters on the training span; recording it explicitly
prevents accidental in-sample reporting and leaves a clean boundary for future
calibration code.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from tradingagents import backtest


@dataclass(frozen=True)
class WalkForwardFold:
    number: int
    train_start: str
    train_end: str
    evaluation_start: str
    evaluation_end: str


def prediction_horizon_sessions(holding_sessions: int, tail_sessions: int) -> int:
    """Sessions to purge after a decision before untouched evaluation data."""
    if holding_sessions < 1 or tail_sessions < 1:
        raise ValueError("holding_sessions and tail_sessions must be >= 1")
    return max(holding_sessions, tail_sessions + 1)


def partition_holdout(
    sessions: list[str], *, holdout_sessions: int, purge_sessions: int
) -> tuple[list[str], list[str], list[str]]:
    """Split research, pre-holdout purge, and a truly untouched holdout."""
    if holdout_sessions < 0 or purge_sessions < 0:
        raise ValueError("holdout_sessions and purge_sessions must be >= 0")
    if holdout_sessions == 0:
        return sessions, [], []
    required = holdout_sessions + purge_sessions
    if required >= len(sessions):
        raise ValueError("holdout plus its purge gap leaves no research sessions")
    holdout = sessions[-holdout_sessions:]
    purge = sessions[-required:-holdout_sessions] if purge_sessions else []
    research = sessions[:-required]
    return research, purge, holdout


def build_folds(
    sessions: list[str],
    *,
    train_sessions: int,
    evaluation_sessions: int,
    embargo_sessions: int = 1,
    prediction_horizon_sessions: int | None = None,
    step_sessions: int | None = None,
) -> list[WalkForwardFold]:
    """Build chronological folds with disjoint out-of-sample evaluation spans."""
    if train_sessions < 1:
        raise ValueError("train_sessions must be >= 1")
    if evaluation_sessions < 1:
        raise ValueError("evaluation_sessions must be >= 1")
    if embargo_sessions < 0:
        raise ValueError("embargo_sessions must be >= 0")
    if prediction_horizon_sessions is not None:
        if prediction_horizon_sessions < 1:
            raise ValueError("prediction_horizon_sessions must be >= 1")
        if embargo_sessions < prediction_horizon_sessions:
            raise ValueError(
                "embargo_sessions must be at least prediction_horizon_sessions "
                "to purge overlapping outcome windows"
            )
    minimum_step = evaluation_sessions + (prediction_horizon_sessions or 0)
    step = step_sessions or minimum_step
    if step < minimum_step:
        raise ValueError(
            "step_sessions must be >= evaluation_sessions plus the prediction horizon"
        )

    ordered = sorted(dict.fromkeys(sessions))
    folds = []
    evaluation_start = train_sessions + embargo_sessions
    number = 1
    while evaluation_start < len(ordered):
        evaluation_end = min(
            evaluation_start + evaluation_sessions - 1, len(ordered) - 1
        )
        if evaluation_end - evaluation_start + 1 < evaluation_sessions:
            break
        train_end = evaluation_start - embargo_sessions - 1
        train_start = train_end - train_sessions + 1
        if train_start < 0:
            break
        folds.append(WalkForwardFold(
            number=number,
            train_start=ordered[train_start],
            train_end=ordered[train_end],
            evaluation_start=ordered[evaluation_start],
            evaluation_end=ordered[evaluation_end],
        ))
        number += 1
        evaluation_start += step
    return folds


def _fold_payload(
    path: Path,
    fold: WalkForwardFold,
    expected_manifest: dict | None = None,
) -> dict | None:
    portfolio_path = path.with_suffix(".portfolio.json")
    if not portfolio_path.exists():
        return None
    try:
        payload = json.loads(portfolio_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    manifest = payload.get("manifest") or {}
    if manifest.get("start") != fold.evaluation_start or \
            manifest.get("end") != fold.evaluation_end:
        return None
    if payload.get("portfolio_fingerprint") != backtest._fingerprint(manifest):
        return None
    if expected_manifest and any(
        manifest.get(key) != value for key, value in expected_manifest.items()
    ):
        return None
    return payload


def _compounded_drawdown(completed: list[dict]) -> float:
    peak = capital = 1.0
    worst = 0.0
    for row in completed:
        equity = row.get("equity") or []
        for point in equity:
            value = capital * float(point["nav"])
            peak = max(peak, value)
            worst = min(worst, value / peak - 1.0)
        capital *= 1.0 + row["metrics"]["total_return"]
    return worst


def summarize_folds(
    folds: list[WalkForwardFold],
    output_dir: Path,
    *,
    minimum_folds: int = 3,
    minimum_positive_fraction: float = 0.6,
    minimum_excess_return: float = 0.0,
    maximum_drawdown: float = 0.20,
    minimum_rank_ic: float = 0.05,
    maximum_placebo_p_value: float = 0.10,
    expected_manifest: dict | None = None,
) -> dict:
    """Collect completed fold artifacts and apply explicit promotion gates."""
    completed = []
    for fold in folds:
        output = output_dir / f"fold-{fold.number:03d}.jsonl"
        payload = _fold_payload(output, fold, expected_manifest)
        if payload is None:
            continue
        metrics = payload["result"]["metrics"]
        completed.append({
            "fold": asdict(fold),
            "metrics": metrics,
            "diagnostics": payload.get("diagnostics") or {},
            "equity": payload["result"].get("equity") or [],
        })

    total_return = 1.0
    benchmark_return = 1.0
    for row in completed:
        total_return *= 1.0 + row["metrics"]["total_return"]
        benchmark_return *= 1.0 + row["metrics"]["benchmark_return"]
    compounded_total = total_return - 1.0
    compounded_benchmark = benchmark_return - 1.0
    compounded_excess = compounded_total - compounded_benchmark
    positive_fraction = (
        sum(row["metrics"]["excess_return"] > 0 for row in completed) / len(completed)
        if completed else 0.0
    )
    worst_fold_drawdown = min(
        (row["metrics"]["max_drawdown"] for row in completed), default=0.0
    )
    compounded_drawdown = _compounded_drawdown(completed)
    rank_ics = [
        row["diagnostics"].get("cross_sectional_rank_ic", {}).get("mean_rank_ic")
        for row in completed
    ]
    valid_rank_ics = [value for value in rank_ics if value is not None]
    mean_rank_ic = (
        sum(valid_rank_ics) / len(valid_rank_ics) if valid_rank_ics else None
    )
    baseline_wins = [
        row["diagnostics"].get("baselines", {}).get("equal_weight", {}).get(
            "observed_minus_baseline_return"
        )
        for row in completed
    ]
    placebo_values = [
        row["diagnostics"].get("ticker_permutation_placebo", {}).get("empirical_p_value")
        for row in completed
    ]
    residual_alphas = [
        row["diagnostics"].get("beta_attribution", {}).get("annualized_residual_alpha")
        for row in completed
    ]

    def passing_fraction(values, predicate) -> float:
        return (
            sum(value is not None and predicate(value) for value in values) / len(completed)
            if completed else 0.0
        )

    baseline_win_fraction = passing_fraction(baseline_wins, lambda value: value > 0)
    placebo_pass_fraction = passing_fraction(
        placebo_values, lambda value: value <= maximum_placebo_p_value
    )
    residual_alpha_fraction = passing_fraction(residual_alphas, lambda value: value > 0)
    gates = {
        "minimum_completed_folds": len(completed) >= minimum_folds,
        "positive_excess_fold_fraction": positive_fraction >= minimum_positive_fraction,
        "minimum_compounded_excess_return": compounded_excess >= minimum_excess_return,
        "maximum_compounded_drawdown": compounded_drawdown >= -maximum_drawdown,
        "minimum_mean_rank_ic": mean_rank_ic is not None and mean_rank_ic >= minimum_rank_ic,
        "beats_equal_weight_fraction": baseline_win_fraction >= minimum_positive_fraction,
        "ticker_placebo_significance_fraction": (
            placebo_pass_fraction >= minimum_positive_fraction
        ),
        "positive_residual_alpha_fraction": (
            residual_alpha_fraction >= minimum_positive_fraction
        ),
    }
    return {
        "schema_version": 1,
        "folds_planned": len(folds),
        "folds_completed": len(completed),
        "compounded_total_return": compounded_total,
        "compounded_benchmark_return": compounded_benchmark,
        "compounded_excess_return": compounded_excess,
        "positive_excess_fold_fraction": positive_fraction,
        "worst_fold_drawdown": worst_fold_drawdown,
        "compounded_max_drawdown": compounded_drawdown,
        "mean_rank_ic": mean_rank_ic,
        "equal_weight_win_fraction": baseline_win_fraction,
        "placebo_pass_fraction": placebo_pass_fraction,
        "positive_residual_alpha_fraction": residual_alpha_fraction,
        "promotion_gates": gates,
        "promotion_ready": bool(gates) and all(gates.values()),
        "folds": completed,
    }


def _backtest_command(args, fold: WalkForwardFold, output: Path) -> list[str]:
    command = [
        sys.executable, "-m", "tradingagents.backtest",
        "--tickers", args.tickers,
        "--start", fold.evaluation_start,
        "--end", fold.evaluation_end,
        "--benchmark", args.benchmark,
        "--analysts", args.analysts,
        "--db", args.db,
        "--output", str(output),
        "--max-runs", str(args.max_runs_per_fold),
        "--replicates", str(args.replicates),
        "--portfolio-mode", args.portfolio_mode,
        "--gross-limit", str(args.gross_limit),
        "--max-weight", str(args.max_weight),
        "--cost-bps", str(args.cost_bps),
        "--slippage-bps", str(args.slippage_bps),
        "--annual-borrow-bps", str(args.annual_borrow_bps),
        "--tail-sessions", str(args.tail_sessions),
        "--holding-sessions", str(args.holding_sessions),
        "--placebo-trials", str(args.placebo_trials),
        "--identity-control", args.identity_control,
    ]
    if args.debug:
        command.append("--debug")
    if args.global_topics_only:
        command.append("--global-topics-only")
    return command


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", required=True)
    parser.add_argument("--start", required=True, help="First available session")
    parser.add_argument("--end", required=True, help="Last available session")
    parser.add_argument("--db", required=True)
    parser.add_argument("--output-dir", default="results/walk-forward")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--train-sessions", type=int, default=60)
    parser.add_argument("--evaluation-sessions", type=int, default=20)
    parser.add_argument(
        "--embargo-sessions", type=int,
        help="Purged sessions between train/evaluation; default is the longest outcome horizon",
    )
    parser.add_argument(
        "--holdout-sessions", type=int, default=20,
        help="Trailing sessions reserved from all folds as a locked final holdout",
    )
    parser.add_argument("--step-sessions", type=int)
    parser.add_argument("--analysts", default="market,social,news")
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--portfolio-mode", default="long-only",
                        choices=("long-only", "long-short", "market-neutral"))
    parser.add_argument("--gross-limit", type=float, default=1.0)
    parser.add_argument("--max-weight", type=float, default=0.25)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--annual-borrow-bps", type=float, default=300.0)
    parser.add_argument("--tail-sessions", type=int, default=1)
    parser.add_argument("--holding-sessions", type=int, default=5)
    parser.add_argument("--placebo-trials", type=int, default=100)
    parser.add_argument("--identity-control", choices=("none", "ticker-mask"), default="none")
    parser.add_argument("--global-topics-only", action="store_true")
    parser.add_argument("--max-runs-per-fold", type=int, default=100)
    parser.add_argument("--minimum-folds", type=int, default=3)
    parser.add_argument("--minimum-positive-fraction", type=float, default=0.6)
    parser.add_argument("--minimum-excess-return", type=float, default=0.0)
    parser.add_argument("--maximum-drawdown", type=float, default=0.20)
    parser.add_argument("--minimum-rank-ic", type=float, default=0.05)
    parser.add_argument("--maximum-placebo-p-value", type=float, default=0.10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    if args.start > args.end:
        parser.error("--start must be on or before --end")
    if args.holdout_sessions < 0:
        parser.error("--holdout-sessions must be >= 0")
    if args.holding_sessions < 1 or args.tail_sessions < 1:
        parser.error("--holding-sessions and --tail-sessions must be >= 1")
    # A portfolio decision enters on the following session, and the simulator
    # consumes ``tail_sessions`` additional opens after that entry.  Reserve
    # tail+1 dates so its last mark cannot land on the first locked holdout day.
    prediction_horizon = prediction_horizon_sessions(
        args.holding_sessions, args.tail_sessions
    )
    embargo_sessions = (
        prediction_horizon if args.embargo_sessions is None else args.embargo_sessions
    )
    if embargo_sessions < prediction_horizon:
        parser.error(
            "--embargo-sessions must be at least the longest holding/tail horizon "
            f"({prediction_horizon})"
        )
    benchmark = backtest._load_prices(args.benchmark, args.start, args.end, 1)
    sessions = backtest._decision_dates(benchmark, args.start, args.end)
    try:
        research_sessions, holdout_purge, holdout = partition_holdout(
            sessions,
            holdout_sessions=args.holdout_sessions,
            purge_sessions=prediction_horizon if args.holdout_sessions else 0,
        )
    except ValueError as exc:
        parser.error(str(exc))
    try:
        folds = build_folds(
            research_sessions,
            train_sessions=args.train_sessions,
            evaluation_sessions=args.evaluation_sessions,
            embargo_sessions=embargo_sessions,
            prediction_horizon_sessions=prediction_horizon,
            step_sessions=args.step_sessions,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if not folds:
        parser.error("date range is too short for one complete walk-forward fold")

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "tickers": [value.strip().upper() for value in args.tickers.split(",")],
        "benchmark": args.benchmark,
        "train_sessions": args.train_sessions,
        "evaluation_sessions": args.evaluation_sessions,
        "prediction_horizon_sessions": prediction_horizon,
        "embargo_sessions": embargo_sessions,
        "holdout_sessions": args.holdout_sessions,
        "holdout_purge_sessions": len(holdout_purge),
        "holdout_purge_start": holdout_purge[0] if holdout_purge else None,
        "holdout_purge_end": holdout_purge[-1] if holdout_purge else None,
        "holdout_start": holdout[0] if holdout else None,
        "holdout_end": holdout[-1] if holdout else None,
        "step_sessions": args.step_sessions or args.evaluation_sessions + prediction_horizon,
        "folds": [asdict(fold) for fold in folds],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    tickers = [value.strip().upper() for value in args.tickers.split(",") if value.strip()]
    analysts = tuple(value.strip() for value in args.analysts.split(",") if value.strip())
    aliases = backtest._identity_aliases(tickers, args.identity_control)
    signal_manifest = backtest._signal_manifest(
        args,
        analysts,
        aliases if args.identity_control == "ticker-mask" else {},
    )
    expected_fold_manifest = {
        "signal_fingerprint": backtest._signal_fingerprint(signal_manifest),
        "tickers": tickers,
        "benchmark": args.benchmark,
        "mode": args.portfolio_mode,
        "gross_limit": args.gross_limit,
        "max_weight": args.max_weight,
        "trading_cost_bps": args.cost_bps,
        "slippage_bps": args.slippage_bps,
        "annual_borrow_bps": args.annual_borrow_bps,
        "tail_sessions": args.tail_sessions,
        "holding_sessions": args.holding_sessions,
        "replicates": args.replicates,
        "placebo_trials": args.placebo_trials,
    }

    for fold in folds:
        output = output_dir / f"fold-{fold.number:03d}.jsonl"
        command = _backtest_command(args, fold, output)
        print(
            f"Fold {fold.number}: train {fold.train_start}..{fold.train_end} · "
            f"evaluate {fold.evaluation_start}..{fold.evaluation_end}"
        )
        if args.dry_run:
            display = command.copy()
            display[display.index("--db") + 1] = "<redacted>"
            print("  " + " ".join(display))
        else:
            subprocess.run(command, check=True)

    if args.dry_run:
        print("Dry run complete; existing fold artifacts were not summarized.")
        return

    summary = summarize_folds(
        folds,
        output_dir,
        minimum_folds=args.minimum_folds,
        minimum_positive_fraction=args.minimum_positive_fraction,
        minimum_excess_return=args.minimum_excess_return,
        maximum_drawdown=args.maximum_drawdown,
        minimum_rank_ic=args.minimum_rank_ic,
        maximum_placebo_p_value=args.maximum_placebo_p_value,
        expected_manifest=expected_fold_manifest,
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(
        f"Completed {summary['folds_completed']}/{summary['folds_planned']} folds · "
        f"promotion_ready={summary['promotion_ready']} · "
        f"locked_holdout={len(holdout)} sessions"
    )


if __name__ == "__main__":
    main()
