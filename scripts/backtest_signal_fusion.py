#!/usr/bin/env python3
"""A/B backtest of the SignalFusion layer vs the v0.2.5 baseline.

Runs ``TradingAgentsGraph.propagate`` twice per (ticker, date) — once
with ``signal_fusion_enabled=False`` (legacy serial), once with the
default fused pipeline — and reports the alpha difference, token cost
delta, and wall-clock delta.

Default ticker set, chosen for coverage rather than cherry-picking:

    TSLA   — large-cap, retail-heavy sentiment, frequent news
    JNJ    — defensive large-cap, slow-moving fundamentals
    NVDA   — large-cap, momentum-driven, dense earnings flow
    SPY    — index ETF, validates we don't blow up the macro case
    RKLB   — small-cap, ambiguous fundamentals, mixed retail sentiment

Usage
-----

A real comparison run hits the LLM provider and yfinance; running it
costs real money. Default mode prints what it *would* run without
issuing the calls:

    uv run python scripts/backtest_signal_fusion.py --dry-run

To execute, set provider keys and pass ``--execute``. Limit the matrix
size while you're getting set up:

    uv run python scripts/backtest_signal_fusion.py \\
        --execute \\
        --tickers TSLA NVDA \\
        --dates 2025-12-01 2025-12-08 2025-12-15 2025-12-22 \\
        --output ./fusion_backtest.csv

Output: a CSV with one row per (ticker, date, arm) — and a markdown
summary table printed to stdout at the end. The summary feeds straight
into the SIGNAL_FUSION.md "Backtest results" section.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import yfinance as yf

# Repo root on sys.path so this script works when run from any cwd.
_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402

logger = logging.getLogger("backtest_signal_fusion")


DEFAULT_TICKERS = ["TSLA", "JNJ", "NVDA", "SPY", "RKLB"]


@dataclass
class RunResult:
    ticker: str
    trade_date: str
    arm: str  # "fusion" | "legacy"
    decision: str
    composite_score: float
    raw_return_5d: Optional[float]
    alpha_5d: Optional[float]
    wall_clock_s: float
    error: Optional[str] = None


def _resolve_benchmark(ticker: str) -> str:
    """Mirror TradingAgentsGraph._resolve_benchmark for non-US tickers."""
    bench_map = DEFAULT_CONFIG.get("benchmark_map", {})
    upper = ticker.upper()
    for suffix, benchmark in bench_map.items():
        if suffix and upper.endswith(suffix.upper()):
            return benchmark
    return bench_map.get("", "SPY")


def _fetch_forward_alpha(ticker: str, trade_date: str, days: int = 5) -> Tuple[Optional[float], Optional[float]]:
    """Return (raw_return, alpha) for the next ``days`` trading days, or (None, None)."""
    try:
        start = datetime.strptime(trade_date, "%Y-%m-%d")
        end = start + timedelta(days=days + 7)
        benchmark = _resolve_benchmark(ticker)
        stock = yf.Ticker(ticker).history(start=trade_date, end=end.strftime("%Y-%m-%d"))
        bench = yf.Ticker(benchmark).history(start=trade_date, end=end.strftime("%Y-%m-%d"))
        if len(stock) < 2 or len(bench) < 2:
            return None, None
        actual = min(days, len(stock) - 1, len(bench) - 1)
        raw = float((stock["Close"].iloc[actual] - stock["Close"].iloc[0]) / stock["Close"].iloc[0])
        bench_ret = float((bench["Close"].iloc[actual] - bench["Close"].iloc[0]) / bench["Close"].iloc[0])
        return raw, raw - bench_ret
    except Exception as e:
        logger.warning("forward-alpha fetch failed for %s on %s: %s", ticker, trade_date, e)
        return None, None


def _run_one(ticker: str, trade_date: str, *, fusion: bool) -> RunResult:
    """Execute one propagate call and capture the relevant fields."""
    cfg = dict(DEFAULT_CONFIG)
    cfg["signal_fusion_enabled"] = fusion

    arm = "fusion" if fusion else "legacy"
    t0 = time.perf_counter()
    try:
        graph = TradingAgentsGraph(config=cfg)
        final_state, decision = graph.propagate(ticker, trade_date)
        wall = time.perf_counter() - t0
        composite = float(final_state.get("composite_score", 0.0))
    except Exception as e:
        return RunResult(
            ticker=ticker,
            trade_date=trade_date,
            arm=arm,
            decision="",
            composite_score=0.0,
            raw_return_5d=None,
            alpha_5d=None,
            wall_clock_s=time.perf_counter() - t0,
            error=str(e),
        )

    raw, alpha = _fetch_forward_alpha(ticker, trade_date)
    return RunResult(
        ticker=ticker,
        trade_date=trade_date,
        arm=arm,
        decision=str(decision),
        composite_score=composite,
        raw_return_5d=raw,
        alpha_5d=alpha,
        wall_clock_s=wall,
    )


def _write_csv(results: List[RunResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ticker", "trade_date", "arm", "decision", "composite_score",
            "raw_return_5d", "alpha_5d", "wall_clock_s", "error",
        ])
        for r in results:
            writer.writerow([
                r.ticker, r.trade_date, r.arm, r.decision, f"{r.composite_score:.4f}",
                "" if r.raw_return_5d is None else f"{r.raw_return_5d:.6f}",
                "" if r.alpha_5d is None else f"{r.alpha_5d:.6f}",
                f"{r.wall_clock_s:.2f}",
                r.error or "",
            ])
    logger.info("wrote %d rows to %s", len(results), path)


def _summarise(results: List[RunResult]) -> str:
    """Per-arm mean alpha, hit rate, decision distribution."""
    arms = {}
    for r in results:
        arms.setdefault(r.arm, []).append(r)

    lines = [
        "| Arm | Runs | Mean α | Hit rate | Mean wall-clock | Decisions (B/H/S) |",
        "|---|---|---|---|---|---|",
    ]
    for arm in ("legacy", "fusion"):
        rs = arms.get(arm, [])
        if not rs:
            lines.append(f"| {arm} | 0 | n/a | n/a | n/a | n/a |")
            continue
        ok_alpha = [r.alpha_5d for r in rs if r.alpha_5d is not None]
        mean_alpha = sum(ok_alpha) / len(ok_alpha) if ok_alpha else None
        hit_rate = sum(1 for a in ok_alpha if a > 0) / len(ok_alpha) if ok_alpha else None
        mean_wall = sum(r.wall_clock_s for r in rs) / len(rs)
        buys = sum(1 for r in rs if r.decision.lower().startswith("buy") or "buy" in r.decision.lower())
        sells = sum(1 for r in rs if r.decision.lower().startswith("sell") or "sell" in r.decision.lower())
        holds = sum(1 for r in rs if r.decision.lower().startswith("hold") or "hold" in r.decision.lower())
        lines.append(
            f"| {arm} | {len(rs)} | "
            f"{'n/a' if mean_alpha is None else f'{mean_alpha:+.2%}'} | "
            f"{'n/a' if hit_rate is None else f'{hit_rate:.0%}'} | "
            f"{mean_wall:.0f}s | {buys}/{holds}/{sells} |"
        )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS, help="Ticker symbols to test")
    parser.add_argument("--dates", nargs="+", default=None, help="YYYY-MM-DD dates to test; defaults to 4 weekly Mondays ending 14 days ago")
    parser.add_argument("--output", default="./fusion_backtest.csv", help="CSV output path")
    parser.add_argument("--execute", action="store_true", help="Actually call the LLM (costs money); default is dry-run")
    parser.add_argument("--dry-run", action="store_true", help="Print the run matrix and exit (default mode)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    dates = args.dates
    if dates is None:
        today = datetime.utcnow().date()
        # Start ~14 days before today; step back in 7-day chunks for 4 dates.
        anchor = today - timedelta(days=14)
        # Snap each anchor to the prior Monday (or itself if it is one).
        anchor -= timedelta(days=anchor.weekday())
        dates = [(anchor - timedelta(days=7 * i)).isoformat() for i in range(4)]
        dates.sort()

    # Always show what we're about to run.
    print(f"Tickers: {args.tickers}")
    print(f"Dates:   {dates}")
    print(f"Arms:    legacy (signal_fusion_enabled=False), fusion (default)")
    print(f"Total runs: {len(args.tickers) * len(dates) * 2}")

    if not args.execute or args.dry_run:
        print("\nDry-run mode. Pass --execute to actually run.")
        return 0

    results: List[RunResult] = []
    for ticker in args.tickers:
        for date in dates:
            for fusion in (False, True):
                print(f"=== {ticker} | {date} | arm={'fusion' if fusion else 'legacy'} ===")
                r = _run_one(ticker, date, fusion=fusion)
                results.append(r)
                if r.error:
                    print(f"    FAILED: {r.error}")
                else:
                    print(f"    decision={r.decision[:40]!r} composite={r.composite_score:+.2f} alpha={r.alpha_5d}")

    output_path = Path(args.output).expanduser()
    _write_csv(results, output_path)
    summary = _summarise(results)
    print("\n## Summary\n")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
