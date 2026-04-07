"""Main entry point for TradingAgents ADK.

Usage:
    uv run main.py                          # Analyze NVDA with defaults
    uv run main.py --company AAPL           # Analyze Apple
    uv run main.py --company TSLA --debug   # Analyze Tesla with debug output
"""

import asyncio
import argparse
import os
import sys
from datetime import date

from dotenv import load_dotenv

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT_CONFIG
from graph.trading_graph import TradingAgentsGraph


async def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="TradingAgents ADK - Multi-Agent Trading Framework")
    parser.add_argument("--company", type=str, default="NVDA", help="Ticker symbol to analyze")
    parser.add_argument("--date", type=str, default=str(date.today()), help="Trade date (yyyy-mm-dd)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--model", type=str, default=DEFAULT_CONFIG["quick_model"], help="Quick-thinking model")
    parser.add_argument("--deep-model", type=str, default=DEFAULT_CONFIG["deep_model"], help="Deep-thinking model")
    parser.add_argument("--debate-rounds", type=int, default=DEFAULT_CONFIG["max_debate_rounds"], help="Bull/Bear debate rounds")
    parser.add_argument("--risk-rounds", type=int, default=DEFAULT_CONFIG["max_risk_rounds"], help="Risk debate rounds")
    args = parser.parse_args()

    # Ensure GOOGLE_API_KEY is set
    if not os.environ.get("GOOGLE_API_KEY"):
        print("Error: GOOGLE_API_KEY environment variable is required.")
        print("Get one at https://aistudio.google.com/apikey")
        return

    print(f"\n{'='*60}")
    print(f"  TradingAgents ADK - Analyzing {args.company}")
    print(f"  Date: {args.date}")
    print(f"  Model: {args.model} / {args.deep_model}")
    print(f"  Debate rounds: {args.debate_rounds} | Risk rounds: {args.risk_rounds}")
    print(f"{'='*60}\n")

    # Create the trading graph
    ta = TradingAgentsGraph(
        model=args.model,
        deep_model=args.deep_model,
        max_debate_rounds=args.debate_rounds,
        max_risk_rounds=args.risk_rounds,
        debug=args.debug,
    )

    # Run the analysis
    print("Running analysis pipeline...")
    print("  Phase 1: Analyst Team (Market + Fundamentals + News) [parallel]")
    print("  Phase 2: Investment Debate (Bull vs Bear)")
    print("  Phase 3: Trader Decision")
    print("  Phase 4: Risk Debate (Aggressive vs Conservative vs Neutral)")
    print("  Phase 5: Portfolio Manager Final Decision")
    print()

    result = await ta.propagate(args.company, args.date)

    # Print final decision (always shown)
    print(f"\n{'='*60}")
    print(f"  FINAL TRADING DECISION for {args.company}")
    print(f"{'='*60}\n")

    final = result["final_decision"]
    if final:
        print(final)
    else:
        print("(No final decision was produced. Run with --debug to investigate.)")

    # In debug mode, print full output from every stage
    if args.debug:
        print(f"\n{'='*60}")
        print("  FULL REPORTS FROM EACH STAGE")
        print(f"{'='*60}")

        reports = [
            ("MARKET REPORT", "market_report"),
            ("FUNDAMENTALS REPORT", "fundamentals_report"),
            ("NEWS REPORT", "news_report"),
            ("INVESTMENT PLAN (Research Manager)", "investment_plan"),
            ("TRADER DECISION", "trader_decision"),
            ("FINAL DECISION (Portfolio Manager)", "final_decision"),
        ]

        for label, key in reports:
            val = result.get(key, "")
            print(f"\n{'━'*60}")
            print(f"  {label}")
            print(f"{'━'*60}")
            if val:
                print(val)
            else:
                print(f"  (empty — {key} was not populated)")
            print()


def _sync_main():
    """Sync wrapper for the entry point (used by pyproject.toml scripts)."""
    asyncio.run(main())


if __name__ == "__main__":
    _sync_main()
