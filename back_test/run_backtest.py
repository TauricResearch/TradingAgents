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
import re
import sys

import pandas as pd
from .engine import BacktestEngine, PROJECT_ROOT
from .metrics import summarize



RESULTS_DIR = PROJECT_ROOT / "back_test" / "trade_route"


def _prompt_output_label(default: str = "B") -> str:
    raw_label = input(f"Output strategy label (e.g. A, B, C) [{default}]: ").strip()
    label = raw_label or default
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("._-")
    return label or default


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
    parser.add_argument(
        "--max-trade-risk-pct", type=float, default=0.020,
        help="Maximum whole-trade risk as a fraction of equity after risk-capped stop recalculation (default 0.020).",
    )
    parser.add_argument(
        "--max-entry-gap-above-plan-pct", type=float, default=0.010,
        help="Cancel entry limit orders when the open gaps above plan by more than this fraction (default 0.010).",
    )
    parser.add_argument(
        "--max-add-gap-above-plan-pct", type=float, default=0.008,
        help="Cancel add limit orders when the open gaps above plan by more than this fraction (default 0.008).",
    )
    parser.add_argument(
        "--obvious-bull-max-entry-gap-pct", type=float, default=0.015,
        help="Maximum market-entry gap allowed for obvious bull strategies (default 0.015).",
    )
    parser.add_argument(
        "--obvious-bull-max-add-gap-pct", type=float, default=0.005,
        help="Maximum market-add gap allowed for obvious bull strategies (default 0.005).",
    )
    parser.add_argument(
        "--entry-signal-ttl-trading-days", type=int, default=2,
        help="Trading-day TTL for pending entry signals (default 2).",
    )
    parser.add_argument(
        "--add-signal-ttl-trading-days", type=int, default=1,
        help="Trading-day TTL for pending add signals (default 1).",
    )
    parser.add_argument(
        "--max-adds-per-trade", type=int, default=2,
        help="Maximum number of adds per open trade (default 2).",
    )
    parser.add_argument(
        "--min-days-between-adds", type=int, default=2,
        help="Minimum trading-day distance between add fills (default 2).",
    )
    parser.add_argument(
        "--max-single-add-pct", type=float, default=8.0,
        help="Maximum equity percent spent by one add order (default 8).",
    )
    parser.add_argument(
        "--max-position-after-add-pct", type=float, default=0.60,
        help="Maximum position value as a fraction of equity after an add (default 0.60).",
    )
    parser.add_argument(
        "--allow-shrinking-volume-adds",
        action="store_true",
        help="Allow add orders during shrinking volume without close-hold confirmation (default blocks them).",
    )
    parser.add_argument(
        "--shrinking-volume-close-hold-days", type=int, default=2,
        help="Required consecutive closes above key level before a shrinking-volume add can fill (default 2).",
    )
    parser.add_argument(
        "--add-key-level-tolerance-pct", type=float, default=0.005,
        help="Tolerance below key level for add close-hold confirmation (default 0.005).",
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
        max_trade_risk_pct=args.max_trade_risk_pct,
        max_single_add_pct=args.max_single_add_pct,
        max_position_after_add_pct=args.max_position_after_add_pct,
        max_adds_per_trade=args.max_adds_per_trade,
        min_days_between_adds=args.min_days_between_adds,
        max_entry_gap_above_plan_pct=args.max_entry_gap_above_plan_pct,
        max_add_gap_above_plan_pct=args.max_add_gap_above_plan_pct,
        obvious_bull_max_entry_gap_pct=args.obvious_bull_max_entry_gap_pct,
        obvious_bull_max_add_gap_pct=args.obvious_bull_max_add_gap_pct,
        entry_signal_ttl_trading_days=args.entry_signal_ttl_trading_days,
        add_signal_ttl_trading_days=args.add_signal_ttl_trading_days,
        block_shrinking_volume_adds=not args.allow_shrinking_volume_adds,
        shrinking_volume_close_hold_days=args.shrinking_volume_close_hold_days,
        add_key_level_tolerance_pct=args.add_key_level_tolerance_pct,
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

    label = _prompt_output_label()
    out_path = RESULTS_DIR / f"{args.ticker}_{effective_start}_{effective_end}_{label}.json"
    run_parameters = {
        "ticker": args.ticker,
        "requested_start_date": args.start,
        "requested_end_date": args.end,
        "effective_start_date": effective_start,
        "effective_end_date": effective_end,
        "initial_capital": args.initial_capital,
        "commission": args.commission,
        "slippage_bps": args.slippage_bps,
        "min_stop_distance_pct": args.min_stop_distance_pct,
        "max_trade_risk_pct": args.max_trade_risk_pct,
        "max_single_add_pct": args.max_single_add_pct,
        "max_position_after_add_pct": args.max_position_after_add_pct,
        "max_adds_per_trade": args.max_adds_per_trade,
        "min_days_between_adds": args.min_days_between_adds,
        "max_entry_gap_above_plan_pct": args.max_entry_gap_above_plan_pct,
        "max_add_gap_above_plan_pct": args.max_add_gap_above_plan_pct,
        "obvious_bull_max_entry_gap_pct": args.obvious_bull_max_entry_gap_pct,
        "obvious_bull_max_add_gap_pct": args.obvious_bull_max_add_gap_pct,
        "entry_signal_ttl_trading_days": args.entry_signal_ttl_trading_days,
        "add_signal_ttl_trading_days": args.add_signal_ttl_trading_days,
        "block_shrinking_volume_adds": not args.allow_shrinking_volume_adds,
        "shrinking_volume_close_hold_days": args.shrinking_volume_close_hold_days,
        "add_key_level_tolerance_pct": args.add_key_level_tolerance_pct,
        "output_label": label,
        "output_path": str(out_path),
    }
    payload = {
        "ticker": args.ticker,
        "requested_start_date": args.start,
        "requested_end_date": args.end,
        "start_date": effective_start,
        "end_date": effective_end,
        "initial_capital": args.initial_capital,
        "commission": args.commission,
        "slippage_bps": args.slippage_bps,
        "min_stop_distance_pct": args.min_stop_distance_pct,
        "max_trade_risk_pct": args.max_trade_risk_pct,
        "max_single_add_pct": args.max_single_add_pct,
        "max_position_after_add_pct": args.max_position_after_add_pct,
        "max_adds_per_trade": args.max_adds_per_trade,
        "min_days_between_adds": args.min_days_between_adds,
        "max_entry_gap_above_plan_pct": args.max_entry_gap_above_plan_pct,
        "max_add_gap_above_plan_pct": args.max_add_gap_above_plan_pct,
        "obvious_bull_max_entry_gap_pct": args.obvious_bull_max_entry_gap_pct,
        "obvious_bull_max_add_gap_pct": args.obvious_bull_max_add_gap_pct,
        "entry_signal_ttl_trading_days": args.entry_signal_ttl_trading_days,
        "add_signal_ttl_trading_days": args.add_signal_ttl_trading_days,
        "block_shrinking_volume_adds": not args.allow_shrinking_volume_adds,
        "shrinking_volume_close_hold_days": args.shrinking_volume_close_hold_days,
        "add_key_level_tolerance_pct": args.add_key_level_tolerance_pct,
        "run_parameters": run_parameters,
        "strategies_loaded": result.strategies_loaded,
        "report": result.report or {},
        "metrics": metrics,
        "trades": result.trades,
        "executions": result.executions,
        "final_pending_orders": result.final_pending_orders or [],
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
    print("  Run parameters:")
    print(f"    ticker:                 {run_parameters['ticker']}")
    print(f"    requested_start_date:   {run_parameters['requested_start_date']}")
    print(f"    requested_end_date:     {run_parameters['requested_end_date']}")
    print(f"    effective_start_date:   {run_parameters['effective_start_date']}")
    print(f"    effective_end_date:     {run_parameters['effective_end_date']}")
    print(f"    initial_capital:        {run_parameters['initial_capital']:g}")
    print(f"    commission:             {run_parameters['commission']:g}")
    print(f"    slippage_bps:           {run_parameters['slippage_bps']:g}")
    print(f"    min_stop_distance_pct:  {run_parameters['min_stop_distance_pct']:g}")
    print(f"    max_trade_risk_pct:     {run_parameters['max_trade_risk_pct']:g}")
    print(f"    add_signal_ttl_days:    {run_parameters['add_signal_ttl_trading_days']}")
    print(f"    block_shrinking_adds:   {run_parameters['block_shrinking_volume_adds']}")
    print(f"    obvious_bull_entry_gap: {run_parameters['obvious_bull_max_entry_gap_pct']:g}")
    print(f"    obvious_bull_add_gap:   {run_parameters['obvious_bull_max_add_gap_pct']:g}")
    print(f"    output_label:           {run_parameters['output_label']}")
    if effective_start != args.start or effective_end != args.end:
        print(f"  Requested range:      {args.start} → {args.end}")
        print(f"  Trading range used:   {effective_start} → {effective_end}")
    print(f"  Strategies loaded:    {result.strategies_loaded}")
    print(f"  Final pending orders: {len(result.final_pending_orders or [])}")
    if result.report:
        print(f"  Extraction failures:  {result.report['extraction_failures']}")
        print(f"  Schema migrations:    {result.report['schema_migrations']}")
        print(f"  Schema rejections:    {result.report['schema_rejections']}")
        print(f"  Invalid SELL orders:  {result.report['invalid_sell_orders']}")
        print(f"  Empty strategies:     {result.report['empty_strategies']}")
        print(f"  Expired order rate:   {result.report['expired_order_rate']:.1%}")
        print(f"  TTL expirations:      {result.report.get('signal_ttl_expired', 0)}")
        print(f"  Gap buy rejected:     {result.report.get('gap_buy_rejected', 0)}")
        print(f"  Shrinking adds rej.:  {result.report.get('add_rejected_shrinking_volume', 0)}")
        print(f"  Risk-size caps:       {result.report.get('entry_capped_risk_size', 0)} entry / {result.report.get('add_capped_risk_size', 0)} add")
        print(f"  Risk stop adjusted:   {result.report.get('risk_stop_adjusted', 0)}")
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
