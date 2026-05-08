from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tradingagents backtest",
        description="Run the TradingAgents pipeline against historical dates.",
    )
    p.add_argument("--ticker", nargs="+", required=True, metavar="TICKER",
                   help="One or more ticker symbols (e.g. NVDA AAPL)")
    p.add_argument("--start", required=True, metavar="YYYY-MM-DD",
                   help="Backtest start date (inclusive)")
    p.add_argument("--end", required=True, metavar="YYYY-MM-DD",
                   help="Backtest end date (inclusive)")
    p.add_argument("--freq", default="monthly",
                   choices=["monthly", "weekly", "biweekly"],
                   help="Signal frequency (default: monthly)")
    p.add_argument("--output", default=None, metavar="PATH",
                   help="JSONL output path (default: ~/.tradingagents/backtests/<hash>.jsonl)")
    p.add_argument("--resume", action="store_true",
                   help="Skip (ticker, date) pairs already in --output with no error")
    p.add_argument("--hold-days", type=int, default=None, metavar="N",
                   help="Override holding period in trading days (default: until next signal)")
    p.add_argument("--workers", type=int, default=2, metavar="N",
                   help="Parallel ticker workers (default: 2)")
    p.add_argument("--risk-free-rate", type=float, default=0.0, metavar="FLOAT",
                   help="Annualised risk-free rate for Sharpe (default: 0.0)")
    p.add_argument("--analysts", nargs="+",
                   choices=["market", "social", "news", "fundamentals"],
                   default=None, metavar="ANALYST",
                   help="Analyst subset (default: all four)")
    return p


def main(argv=None) -> None:
    from tradingagents.backtesting import BacktestEngine, BacktestReport

    parser = build_parser()
    args = parser.parse_args(argv)

    engine = BacktestEngine(
        tickers=args.ticker,
        start_date=args.start,
        end_date=args.end,
        freq=args.freq,
        analysts=args.analysts,
        max_workers=args.workers,
        output_file=args.output,
    )

    print(
        f"Backtesting {args.ticker}  {args.start} → {args.end}  "
        f"freq={args.freq}  workers={args.workers}"
    )
    results = engine.run(resume=args.resume)

    if not results:
        print("No new results — all dates already completed. Use --resume to skip.")
        return

    report = BacktestReport(results, risk_free_rate=args.risk_free_rate)
    summary = report.compute(hold_days_override=args.hold_days)

    print("\n=== Backtest Summary ===")
    print(f"Signals:   {summary.signal_counts}")
    print(f"Errors:    {summary.error_count}")
    if summary.win_rate is not None:
        print(f"Win rate:  {summary.win_rate:.1%}")
    if summary.mean_return is not None:
        print(f"Mean ret:  {summary.mean_return:.2%}")
    if summary.mean_alpha is not None:
        print(f"Mean α:    {summary.mean_alpha:.2%}")
    if summary.sharpe_ratio is not None:
        print(f"Sharpe:    {summary.sharpe_ratio:.2f}")
    if summary.max_drawdown is not None:
        print(f"Max DD:    {summary.max_drawdown:.2%}")

    output_path = Path(engine.output_file)
    summary_path = output_path.with_name(output_path.stem + "_summary.json")
    summary_path.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
    print(f"\nResults:  {engine.output_file}")
    print(f"Summary:  {summary_path}")
