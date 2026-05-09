"""CLI entry point: replay strategies and emit performance metrics.

Example:
    python -m back_test.run_backtest --ticker NVDA --start 2024-01-01 --end 2024-12-31 \
        [--initial-capital 100000]

Outputs:
    back_test/results/{TICKER}_{START}_{END}.json — equity curve + trades + metrics
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd
from .engine import BacktestEngine, PROJECT_ROOT
from .metrics import summarize



RESULTS_DIR = PROJECT_ROOT / "back_test" / "trade_route"


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay TradingAgents weekly strategies on historical OHLCV.")
    parser.add_argument("--ticker", required=True, help="Stock ticker (must match strategy filenames).")
    parser.add_argument("--start", required=True, help="Backtest start date (YYYY-MM-DD).")
    parser.add_argument("--end", required=True, help="Backtest end date (YYYY-MM-DD).")
    parser.add_argument(
        "--initial-capital", type=float, default=100_000.0,
        help="Starting cash (default 100000).",
    )
    parser.add_argument(
        "--commission", type=float, default=0.0,
        help="Flat commission charged per fill in dollars (default 0).",
    )
    parser.add_argument(
        "--slippage-bps", type=float, default=0.0,
        help="Slippage in basis points applied against each fill (default 0).",
    )
    parser.add_argument(
        "--min-stop-distance-pct", type=float, default=0.0,
        help="Floor stop-loss distance as fraction of reference price (e.g. 0.025 = 2.5%%). 0 disables.",
    )
    args = parser.parse_args()

    engine = BacktestEngine(
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.initial_capital,
        commission=args.commission,
        slippage_bps=args.slippage_bps,
        min_stop_distance_pct=args.min_stop_distance_pct,
    )
    try:
        result = engine.run()
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    metrics = summarize(result.equity_curve["Equity"], result.trades)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    effective_start = result.effective_start_date or args.start
    effective_end = result.effective_end_date or args.end
    out_path = RESULTS_DIR / f"{args.ticker}_{effective_start}_{effective_end}_B.json"
    payload = {
        "ticker": args.ticker,
        "requested_start_date": args.start,
        "requested_end_date": args.end,
        "start_date": effective_start,
        "end_date": effective_end,
        "initial_capital": args.initial_capital,
        "commission": args.commission,
        "slippage_bps": args.slippage_bps,
        "strategies_loaded": result.strategies_loaded,
        "report": result.report or {},
        "metrics": metrics,
        "trades": result.trades,
        "executions": result.executions,
        "equity_curve": [
            {
                "date": row.Date.strftime("%Y-%m-%d"),
                "equity": float(row.Equity),
                "cash": float(row.Cash),
                "position": float(row.Position),
                "mark_price": float(row.MarkPrice),
            }
            for row in result.equity_curve.itertuples(index=False)
        ],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"\n=== Backtest Results — {args.ticker} ({effective_start} → {effective_end}) ===")
    if effective_start != args.start or effective_end != args.end:
        print(f"  Requested range:      {args.start} → {args.end}")
        print(f"  Trading range used:   {effective_start} → {effective_end}")
    print(f"  Strategies loaded:    {result.strategies_loaded}")
    if result.report:
        print(f"  Extraction failures:  {result.report['extraction_failures']}")
        print(f"  Schema migrations:    {result.report['schema_migrations']}")
        print(f"  Schema rejections:    {result.report['schema_rejections']}")
        print(f"  Invalid SELL orders:  {result.report['invalid_sell_orders']}")
        print(f"  Empty strategies:     {result.report['empty_strategies']}")
        print(f"  Expired order rate:   {result.report['expired_order_rate']:.1%}")
        audit = result.report.get("bias_audit", {})
        timing = audit.get("event_timing", {})
        execution = audit.get("execution_quality", {})
        print(f"  Same-bar fills:       {timing.get('same_bar_signal_fills', 0)}")
        print(f"  Current-close fills:  {execution.get('current_close_fills', 0)}")
    print(f"  Trading days:         {metrics['n_observations']}")
    print(f"  Total return:         {metrics['total_return']:.2%}")
    print(f"  Annualized return:    {metrics['annualized_return']:.2%}")
    print(f"  Sharpe ratio:         {metrics['sharpe_ratio']:.3f}")
    print(f"  Max drawdown:         {metrics['max_drawdown']:.2%}")
    if metrics.get("n_trades"):
        wr = metrics.get("win_rate")
        wr_str = f"{wr:.1%}" if wr is not None else "n/a"
        print(f"  Trades closed:        {metrics['n_trades']}  (win rate: {wr_str})")
    print(f"\nResults JSON written to: {out_path}")


if __name__ == "__main__":
    main()
