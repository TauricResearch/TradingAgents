"""Reproducible backtest runner for the full TradingAgents graph.

Usage:
    python scripts/backtest.py --tickers NVDA,AAPL --start 2024-01-01 --end 2024-03-29 --every 7
    python scripts/backtest.py --tickers BTC-USD --start 2025-01-01 --end 2025-06-30 --asset-type crypto
    python scripts/backtest.py --tickers NVDA --start 2024-01-01 --end 2024-03-29 --quick-model gpt-5.4-mini

Notes:
- Every (ticker, date) cell runs the full multi-agent graph (10+ LLM calls),
  so keep the grid small or use a cheap quick model.
- The memory log is disabled during backtests; results land in the CSV and
  the markdown summary written under ``--out`` (default ``results/backtest``).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from tradingagents.evaluation import generate_dates, run_backtest


def _parse_date(value: str) -> None:
    datetime.strptime(value, "%Y-%m-%d")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", required=True, help="Comma-separated tickers, e.g. NVDA,AAPL")
    parser.add_argument("--start", required=True, help="First analysis date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Last analysis date, YYYY-MM-DD (inclusive)")
    parser.add_argument("--every", type=int, default=7, help="Days between analysis dates (default: 7)")
    parser.add_argument("--holding-days", type=int, default=5, help="Holding period for returns (default: 5)")
    parser.add_argument("--asset-type", choices=("stock", "crypto"), default="stock")
    parser.add_argument("--llm-provider", default=None, help="Override llm_provider")
    parser.add_argument("--quick-model", default=None, help="Override quick_think_llm")
    parser.add_argument("--deep-model", default=None, help="Override deep_think_llm")
    parser.add_argument("--out", default="results/backtest", help="Output directory (default: results/backtest)")
    args = parser.parse_args()

    _parse_date(args.start)
    _parse_date(args.end)
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        parser.error("--tickers must contain at least one ticker")

    dates = generate_dates(args.start, args.end, every_n_days=args.every)
    config = {}
    if args.llm_provider:
        config["llm_provider"] = args.llm_provider
    if args.quick_model:
        config["quick_think_llm"] = args.quick_model
    if args.deep_model:
        config["deep_think_llm"] = args.deep_model

    cells = len(tickers) * len(dates)
    print(f"Backtest grid: {len(tickers)} ticker(s) x {len(dates)} date(s) = {cells} runs")
    print(f"Asset type: {args.asset_type} | holding days: {args.holding_days}")
    print("Each run invokes the full multi-agent graph; this can take a while.\n")

    df, summary = run_backtest(
        tickers=tickers,
        dates=dates,
        config=config,
        holding_days=args.holding_days,
        asset_type=args.asset_type,
        save_dir=args.out,
    )

    out_dir = Path(args.out)
    print(f"\nResults written to {out_dir / 'backtest_results.csv'}")
    print(f"Summary written to {out_dir / 'backtest_summary.md'}\n")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
