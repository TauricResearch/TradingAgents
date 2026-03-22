"""
Centillion Investment Partners - Portfolio Analysis Runner

Runs the TradingAgents framework across all portfolio + watchlist tickers
and outputs buy/sell/hold recommendations.

Usage:
    # Analyze full portfolio + watchlist
    python centillion_run.py

    # Analyze a single ticker
    python centillion_run.py --ticker CVLT

    # Analyze only the watchlist
    python centillion_run.py --watchlist-only

    # Analyze only US names
    python centillion_run.py --region us

    # Custom analysis date
    python centillion_run.py --date 2025-03-21
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from centillion_config import (
    ALL_PORTFOLIO,
    ALL_TICKERS,
    ALL_WATCHLIST,
    CENTILLION_CONFIG,
    EU_PORTFOLIO,
    EU_WATCHLIST,
    US_PORTFOLIO,
    US_WATCHLIST,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph


def parse_args():
    parser = argparse.ArgumentParser(
        description="Centillion Investment Partners - Trading Agent Analysis"
    )
    parser.add_argument("--ticker", type=str, help="Analyze a single ticker")
    parser.add_argument(
        "--watchlist-only", action="store_true", help="Only analyze watchlist"
    )
    parser.add_argument(
        "--portfolio-only", action="store_true", help="Only analyze current holdings"
    )
    parser.add_argument(
        "--region",
        choices=["us", "eu", "all"],
        default="all",
        help="Region filter (default: all)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Analysis date in YYYY-MM-DD format (default: yesterday)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path for JSON results",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug output from agents"
    )
    return parser.parse_args()


def get_tickers(args):
    """Determine which tickers to analyze based on flags."""
    if args.ticker:
        return [args.ticker.upper()]

    region = args.region

    if args.portfolio_only:
        if region == "us":
            return US_PORTFOLIO
        elif region == "eu":
            return EU_PORTFOLIO
        return ALL_PORTFOLIO

    if args.watchlist_only:
        if region == "us":
            return US_WATCHLIST
        elif region == "eu":
            return EU_WATCHLIST
        return ALL_WATCHLIST

    # Default: everything
    if region == "us":
        return US_PORTFOLIO + US_WATCHLIST
    elif region == "eu":
        return EU_PORTFOLIO + EU_WATCHLIST
    return ALL_TICKERS


def get_analysis_date(args):
    """Get the analysis date — defaults to yesterday (last trading day approximation)."""
    if args.date:
        return args.date
    yesterday = datetime.now() - timedelta(days=1)
    # Skip weekends
    if yesterday.weekday() == 6:  # Sunday
        yesterday -= timedelta(days=2)
    elif yesterday.weekday() == 5:  # Saturday
        yesterday -= timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def run_analysis(tickers, date, debug=False):
    """Run the trading agents analysis on each ticker."""
    ta = TradingAgentsGraph(debug=debug, config=CENTILLION_CONFIG)

    results = {}
    total = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        print(f"\n{'='*60}")
        print(f"  [{i}/{total}] Analyzing {ticker} as of {date}")
        print(f"{'='*60}\n")

        try:
            _, decision = ta.propagate(ticker, date)
            results[ticker] = {
                "decision": decision,
                "date": date,
                "status": "success",
                "in_portfolio": ticker in ALL_PORTFOLIO,
            }

            # Print summary
            print(f"\n  >> {ticker}: {_extract_signal(decision)}")

        except Exception as e:
            print(f"\n  >> {ticker}: ERROR - {e}")
            results[ticker] = {
                "decision": str(e),
                "date": date,
                "status": "error",
                "in_portfolio": ticker in ALL_PORTFOLIO,
            }

    return results


def _extract_signal(decision_text):
    """Extract the BUY/SELL/HOLD signal from the decision text."""
    text_upper = decision_text.upper() if isinstance(decision_text, str) else ""
    for signal in ["BUY", "SELL", "HOLD"]:
        if signal in text_upper:
            return signal
    return "UNCLEAR"


def print_summary(results):
    """Print a clean summary table of all results."""
    print(f"\n\n{'='*70}")
    print("  CENTILLION INVESTMENT PARTNERS — ANALYSIS SUMMARY")
    print(f"{'='*70}\n")

    buys, sells, holds, errors = [], [], [], []

    for ticker, res in results.items():
        if res["status"] == "error":
            errors.append(ticker)
            continue

        signal = _extract_signal(res["decision"])
        tag = " [HELD]" if res["in_portfolio"] else " [WATCH]"

        if signal == "BUY":
            buys.append(f"  {ticker}{tag}")
        elif signal == "SELL":
            sells.append(f"  {ticker}{tag}")
        else:
            holds.append(f"  {ticker}{tag}")

    if buys:
        print("BUY signals:")
        print("\n".join(buys))
    if sells:
        print("\nSELL signals:")
        print("\n".join(sells))
    if holds:
        print("\nHOLD signals:")
        print("\n".join(holds))
    if errors:
        print(f"\nErrors: {', '.join(errors)}")

    print(f"\n{'='*70}\n")


def save_results(results, output_path):
    """Save results to JSON file."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to {output_path}")


def main():
    args = parse_args()
    tickers = get_tickers(args)
    date = get_analysis_date(args)

    print(f"\n  Centillion Investment Partners — TradingAgents Analysis")
    print(f"  Date: {date}")
    print(f"  Tickers ({len(tickers)}): {', '.join(tickers)}")
    print(f"  LLM: {CENTILLION_CONFIG['llm_provider']} / {CENTILLION_CONFIG['deep_think_llm']}")
    print()

    results = run_analysis(tickers, date, debug=args.debug)
    print_summary(results)

    # Save results
    output_path = args.output or f"results/centillion_{date}.json"
    save_results(results, output_path)


if __name__ == "__main__":
    main()
