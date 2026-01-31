#!/usr/bin/env python3
"""
Nifty 50 Stock Recommendation CLI.

This script runs the Nifty 50 recommendation system to predict all Nifty 50 stocks
and select the ones with highest short-term growth potential using Claude Opus 4.5.

Usage:
    # Full run (all 50 stocks)
    python nifty50_recommend.py --date 2025-01-30

    # Test with specific stocks
    python nifty50_recommend.py --stocks TCS,INFY,RELIANCE --date 2025-01-30

    # Quiet mode (less output)
    python nifty50_recommend.py --date 2025-01-30 --quiet
"""

import argparse
import sys
from datetime import datetime


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Nifty 50 Stock Recommendation System using Claude Opus 4.5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Analyze all 50 Nifty stocks
    python nifty50_recommend.py --date 2025-01-30

    # Analyze specific stocks only
    python nifty50_recommend.py --stocks TCS,INFY,RELIANCE --date 2025-01-30

    # Save results to custom directory
    python nifty50_recommend.py --date 2025-01-30 --output ./my_results

    # Quick test with 3 stocks
    python nifty50_recommend.py --stocks TCS,INFY,RELIANCE --date 2025-01-30
        """
    )

    parser.add_argument(
        "--date",
        "-d",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Analysis date in YYYY-MM-DD format (default: today)"
    )

    parser.add_argument(
        "--stocks",
        "-s",
        type=str,
        default=None,
        help="Comma-separated list of stock symbols to analyze (default: all 50)"
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Directory to save results (default: ./results/nifty50_recommendations)"
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output"
    )

    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save results to disk"
    )

    parser.add_argument(
        "--test-credentials",
        action="store_true",
        help="Only test Claude credentials and exit"
    )

    return parser.parse_args()


def test_credentials():
    """Test if Claude credentials are valid."""
    from tradingagents.nifty50_recommender import get_claude_credentials

    try:
        token = get_claude_credentials()
        print(f"✓ Claude credentials found")
        print(f"  Token prefix: {token[:20]}...")
        return True
    except FileNotFoundError as e:
        print(f"✗ Credentials file not found: {e}")
        return False
    except KeyError as e:
        print(f"✗ Invalid credentials format: {e}")
        return False
    except Exception as e:
        print(f"✗ Error reading credentials: {e}")
        return False


def main():
    """Main entry point."""
    args = parse_args()

    # Test credentials mode
    if args.test_credentials:
        success = test_credentials()
        sys.exit(0 if success else 1)

    # Validate date format
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD")
        sys.exit(1)

    # Parse stock subset
    stock_subset = None
    if args.stocks:
        stock_subset = [s.strip().upper() for s in args.stocks.split(",")]
        print(f"Analyzing subset: {', '.join(stock_subset)}")

    # Import the simplified recommender (works with Claude Max subscription)
    try:
        from tradingagents.nifty50_simple_recommender import run_recommendation
    except ImportError as e:
        print(f"Error importing recommender module: {e}")
        print("Make sure you're running from the TradingAgents directory")
        sys.exit(1)

    # Run the recommendation
    try:
        predictions, ranking = run_recommendation(
            trade_date=args.date,
            stock_subset=stock_subset,
            save_results=not args.no_save,
            results_dir=args.output,
            verbose=not args.quiet
        )

        # Print summary
        if not args.quiet:
            print("\n" + "="*60)
            print("SUMMARY")
            print("="*60)

            successful = sum(1 for p in predictions.values() if not p.get("error"))
            print(f"Stocks analyzed: {successful}/{len(predictions)}")

            # Count decisions
            decisions = {}
            for p in predictions.values():
                if not p.get("error"):
                    decision = str(p.get("decision", "UNKNOWN"))
                    decisions[decision] = decisions.get(decision, 0) + 1

            print("\nDecision breakdown:")
            for decision, count in sorted(decisions.items()):
                print(f"  {decision}: {count}")

    except FileNotFoundError as e:
        print(f"\nError: {e}")
        print("\nTo authenticate with Claude, run:")
        print("  claude auth login")
        sys.exit(1)
    except Exception as e:
        print(f"\nError running recommendation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
