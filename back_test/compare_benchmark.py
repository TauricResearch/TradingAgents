from __future__ import annotations

import argparse
import json
import math
import numbers
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    script_dir_str = str(script_dir)
    if script_dir_str in sys.path:
        sys.path.remove(script_dir_str)
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "matplotlib"))

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


import pandas as pd
import yfinance as yf

from tradingagents.dataflows.stockstats_utils import load_ohlcv, yf_retry

try:
    from .engine import PROJECT_ROOT
    from .metrics import summarize
except ImportError:
    from back_test.engine import PROJECT_ROOT
    from back_test.metrics import summarize

DATA_DIR = PROJECT_ROOT / "back_test" / "trade_route"
RESULTS_DIR = PROJECT_ROOT / "back_test" / "results"
PLOTS_DIR = RESULTS_DIR / "plots"
METRICS_DIR = RESULTS_DIR / "metrics"
BENCHMARKS = ["^GSPC", "^IXIC"] # "^IXIC"


def _replace_nonfinite_numbers(value):
    if isinstance(value, dict):
        return {k: _replace_nonfinite_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_nonfinite_numbers(v) for v in value]
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        numeric = float(value)
        if not math.isfinite(numeric):
            return 0.0
    return value


def _load_benchmark_close(benchmark: str, start: str, end: str) -> pd.Series:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    bench_raw = load_ohlcv(benchmark, end)
    bench_raw = bench_raw[
        (bench_raw["Date"] >= start_ts)
        & (bench_raw["Date"] <= end_ts)
    ].set_index("Date").sort_index()

    if not bench_raw.empty:
        return bench_raw["Close"].rename(benchmark)

    fresh = yf_retry(lambda: yf.download(
        benchmark,
        start=start_ts.strftime("%Y-%m-%d"),
        end=(end_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        multi_level_index=False,
        progress=False,
        auto_adjust=True,
    ))

    if fresh.empty:
        return pd.Series(dtype=float, name=benchmark)

    fresh = fresh.reset_index()
    fresh["Date"] = pd.to_datetime(fresh["Date"], errors="coerce")
    fresh["Close"] = pd.to_numeric(fresh["Close"], errors="coerce")
    fresh = fresh.dropna(subset=["Date", "Close"]).set_index("Date").sort_index()

    return fresh["Close"].rename(benchmark)


def _strategy_path_from_spec(ticker: str, start: str, end: str, spec: str) -> Path:
    path = Path(spec).expanduser()
    if path.exists():
        return path
    return DATA_DIR / f"{ticker}_{start}_{end}_{spec}.json"


def _strategy_label_from_path(ticker: str, start: str, end: str, path: Path) -> str:
    prefix = f"{ticker}_{start}_{end}_"
    stem = path.stem
    if stem.startswith(prefix):
        return stem[len(prefix):]
    return stem


def _discover_strategy_specs(ticker: str, start: str, end: str) -> list[str]:
    prefix = f"{ticker}_{start}_{end}_"
    return sorted(
        path.stem[len(prefix):]
        for path in DATA_DIR.glob(f"{prefix}*.json")
    )


def _load_strategy_equity(path: Path, label: str) -> tuple[pd.Series, list]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    strat_df = pd.DataFrame(data["equity_curve"])
    if strat_df.empty:
        raise ValueError(f"Strategy file has an empty equity_curve: {path}")

    strat_df["date"] = pd.to_datetime(strat_df["date"])
    strat_df = strat_df.set_index("date").sort_index()
    return strat_df["equity"].rename(label), data.get("trades")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare one or more backtest strategy routes against buy-and-hold benchmarks."
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. AAPL or SPY.")
    parser.add_argument("--start", required=True, help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end", required=True, help="End date in YYYY-MM-DD format.")
    return parser.parse_args()


def _prompt_for_inputs(args: argparse.Namespace | None = None) -> tuple[str, str, str, list[str]]:
    args = args or _parse_args()
    ticker = args.ticker.strip().upper()
    start = args.start.strip()
    end = args.end.strip()

    discovered = _discover_strategy_specs(ticker, start, end)
    if discovered:
        print("Available strategy labels:", ", ".join(discovered))

    raw_specs = input(
        "Strategy labels or JSON paths, comma-separated "
        "(blank = all available labels): "
    ).strip()
    specs = [item.strip() for item in raw_specs.split(",") if item.strip()]
    if not specs:
        specs = discovered

    return ticker, start, end, specs


def main(ticker: str, start: str, end: str, strategy_specs: list[str]) -> None:
    if not strategy_specs:
        print(
            f"ERROR: No strategy files selected and none found in {DATA_DIR} "
            f"for {ticker}_{start}_{end}_*.json",
            file=sys.stderr,
        )
        sys.exit(1)

    strategy_series = []
    strategy_trades = {}
    missing_paths = []

    for spec in strategy_specs:
        path = _strategy_path_from_spec(ticker, start, end, spec)
        if not path.exists():
            missing_paths.append(path)
            continue
        label = _strategy_label_from_path(ticker, start, end, path)
        series, trades = _load_strategy_equity(path, label)
        strategy_series.append(series)
        strategy_trades[label] = trades

    if missing_paths:
        print("ERROR: Strategy file(s) not found:", file=sys.stderr)
        for path in missing_paths:
            print(f"  {path}", file=sys.stderr)
        sys.exit(1)

    if not strategy_series:
        print("ERROR: No strategy data loaded.", file=sys.stderr)
        sys.exit(1)

    buy_hold_label = f"{ticker}_buy_hold"
    ticker_buy_hold = _load_benchmark_close(
        ticker,
        start,
        end,
    ).rename(buy_hold_label)

    benchmark_series = [
        _load_benchmark_close(benchmark, start, end)
        for benchmark in BENCHMARKS
    ]
    all_benchmarks = [buy_hold_label] + BENCHMARKS

    aligned = pd.concat(
        strategy_series + [ticker_buy_hold] + benchmark_series,
        axis=1,
        join="inner",
    ).dropna()

    if aligned.empty:
        print(
            "ERROR: No overlapping trading dates between strategy and benchmarks.",
            file=sys.stderr,
        )
        sys.exit(1)

    strategy_metrics = {}
    for series in strategy_series:
        strategy_metrics[series.name] = summarize(
            aligned[series.name],
            strategy_trades.get(series.name),
        )

    benchmark_metrics = {}
    alpha = {}

    for benchmark in all_benchmarks:
        bench_aligned = aligned[benchmark]
        bench_metrics = summarize(bench_aligned)
        benchmark_metrics[benchmark] = bench_metrics

    for strategy_label, strat_metrics in strategy_metrics.items():
        alpha[strategy_label] = {}
        for benchmark in all_benchmarks:
            bench_metrics = benchmark_metrics[benchmark]
            alpha[strategy_label][benchmark] = {
                "alpha_total": (
                    strat_metrics["total_return"]
                    - bench_metrics["total_return"]
                ),
                "alpha_annualized": (
                    strat_metrics["annualized_return"]
                    - bench_metrics["annualized_return"]
                ),
            }

    comparison = {
        "ticker": ticker,
        "strategies": list(strategy_metrics.keys()),
        "benchmarks": all_benchmarks,
        "start_date": start,
        "end_date": end,
        "strategy_metrics": strategy_metrics,
        "benchmark_metrics": benchmark_metrics,
        "alpha": alpha,
    }

    comparison = _replace_nonfinite_numbers(comparison)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    run_tag = datetime.now().strftime("%H%M%S")

    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)

    start_year = start_dt.year
    start_date_str = start_dt.strftime("%Y-%m-%d")
    end_year = end_dt.year
    end_date_str = end_dt.strftime("%Y-%m-%d")

    if start_year == end_year:
        year = f"{start_year}"
        label_part = "_".join(comparison["strategies"])
        base_stem = (
            f"{ticker}_compare_{label_part}_{year}_{start_date_str}_{end_date_str}_{run_tag}"
        )
    elif start_year != end_year:
        label_part = "_".join(comparison["strategies"])
        base_stem = (
            f"{ticker}_compare_{label_part}_{start_year}_{end_year}_{run_tag}"
        )

    metrics_path = METRICS_DIR / f"{base_stem}_metrics.json"

    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, allow_nan=False)

    plot_path = PLOTS_DIR / f"{base_stem}.png"

    plot_written = False

    if plt is not None:
        fig, ax = plt.subplots(figsize=(20, 6))

        for column in aligned.columns:
            norm = aligned[column] / aligned[column].iloc[0] * 100.0

            if column in comparison["strategies"]:
                label = f"{ticker} {column}"
                linewidth = 1.0
            elif column == buy_hold_label:
                label = f"{ticker} buy & hold"
                linewidth = 0.6
            else:
                label = column
                linewidth = 0.6

            ax.plot(
                norm.index,
                norm.values,
                label=label,
                linewidth=linewidth,
                alpha=0.9,
            )

        ax.set_title(
            f"strategies for {ticker} vs buy & hold, ^IXIC, and ^GSPC "
            f"({start} → {end})"
        )
        ax.set_xlabel("Date")
        ax.set_ylabel("Normalized value (start = 100)")
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax.grid(True, alpha=0.3)
        ax.legend()

        fig.tight_layout()
        fig.savefig(plot_path, dpi=130)
        plt.close(fig)
        plot_written = True

    print(f"\n=== Strategies vs Benchmarks ({start} → {end}) ===")
    for strategy_label, metrics in comparison["strategy_metrics"].items():
        print(
            f"  {strategy_label:<19}total:{metrics['total_return']:>9.2%}   "
            f"annualized {metrics['annualized_return']:>7.2%}   "
            f"sharpe {metrics['sharpe_ratio']:.3f}"
        )

    for benchmark in all_benchmarks:
        bench_metrics = comparison["benchmark_metrics"][benchmark]
        label = f"{ticker} buy & hold" if benchmark == buy_hold_label else benchmark

        print(
            f"  {label:<19}total:{bench_metrics['total_return']:>9.2%}   "
            f"annualized {bench_metrics['annualized_return']:>7.2%}   "
            f"sharpe {bench_metrics['sharpe_ratio']:.3f}"
        )

    print("\n=== Alpha ===")
    for strategy_label, alpha_by_benchmark in comparison["alpha"].items():
        for benchmark in all_benchmarks:
            alpha_metrics = alpha_by_benchmark[benchmark]
            label = f"{ticker} buy & hold" if benchmark == buy_hold_label else benchmark
            print(
                f"  {strategy_label} vs {label:<19}"
                f"total: {alpha_metrics['alpha_total']:>8.2%}   "
                f"annualized: {alpha_metrics['alpha_annualized']:>8.2%}"
            )

    if plot_written:
        print(f"\nPlot:    {plot_path}")
    else:
        print("\nPlot:    skipped (matplotlib is not installed in this Python environment)")

    print(f"Metrics: {metrics_path}")


if __name__ == "__main__":
    ticker, start, end, strategy_specs = _prompt_for_inputs(_parse_args())
    main(ticker, start, end, strategy_specs)
