"""
Centillion Investment Partners - Virtual Portfolio Tracker

Maintains a paper-trading portfolio based on TradingAgents signals.
Tracks performance over time against benchmarks to evaluate whether
the agent-driven strategy generates alpha.

Usage:
    # Initialize a new virtual portfolio with $1M
    python centillion_portfolio_tracker.py init --cash 1000000

    # Record today's signals and update positions
    python centillion_portfolio_tracker.py update

    # Show current portfolio and performance
    python centillion_portfolio_tracker.py status

    # Show performance vs benchmarks
    python centillion_portfolio_tracker.py performance
"""

import argparse
import json
import os
from datetime import datetime, timedelta

import yfinance as yf

PORTFOLIO_FILE = "results/virtual_portfolio.json"


def load_portfolio():
    if not os.path.exists(PORTFOLIO_FILE):
        print("No portfolio found. Run 'init' first.")
        return None
    with open(PORTFOLIO_FILE) as f:
        return json.load(f)


def save_portfolio(portfolio):
    os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, indent=2, default=str)


def cmd_init(args):
    """Initialize a fresh virtual portfolio."""
    portfolio = {
        "inception_date": datetime.now().strftime("%Y-%m-%d"),
        "initial_cash": args.cash,
        "cash": args.cash,
        "positions": {},  # ticker -> {"shares": n, "avg_cost": x, "entry_date": d}
        "history": [],  # list of {date, action, ticker, shares, price, total_value}
        "daily_nav": [],  # list of {date, nav, benchmark_values: {}}
    }
    save_portfolio(portfolio)
    print(f"Virtual portfolio initialized with ${args.cash:,.0f} cash.")
    print(f"Saved to {PORTFOLIO_FILE}")


def cmd_update(args):
    """Apply signals from the latest analysis run to the portfolio."""
    portfolio = load_portfolio()
    if not portfolio:
        return

    # Load latest analysis results
    results_dir = "results"
    result_files = sorted(
        [f for f in os.listdir(results_dir) if f.startswith("centillion_") and f.endswith(".json") and f != "virtual_portfolio.json"],
        reverse=True,
    )

    if not result_files:
        print("No analysis results found. Run centillion_run.py first.")
        return

    latest_file = os.path.join(results_dir, result_files[0])
    print(f"Using signals from: {latest_file}")

    with open(latest_file) as f:
        signals = json.load(f)

    date = datetime.now().strftime("%Y-%m-%d")
    position_size = portfolio["cash"] + _total_position_value(portfolio)
    target_per_position = position_size * 0.05  # 5% position sizing (long-only)

    actions_taken = []

    for ticker, data in signals.items():
        if data["status"] == "error":
            continue

        signal = _extract_signal(data.get("decision", ""))

        if signal == "BUY" and ticker not in portfolio["positions"]:
            # Buy new position — allocate ~5% of portfolio
            try:
                price = _get_current_price(ticker)
                if price and portfolio["cash"] >= target_per_position:
                    shares = int(target_per_position / price)
                    if shares > 0:
                        cost = shares * price
                        portfolio["cash"] -= cost
                        portfolio["positions"][ticker] = {
                            "shares": shares,
                            "avg_cost": price,
                            "entry_date": date,
                        }
                        actions_taken.append(f"  BUY  {shares} {ticker} @ ${price:.2f} = ${cost:,.0f}")
                        portfolio["history"].append({
                            "date": date, "action": "BUY", "ticker": ticker,
                            "shares": shares, "price": price,
                        })
            except Exception as e:
                print(f"  Could not buy {ticker}: {e}")

        elif signal == "SELL" and ticker in portfolio["positions"]:
            # Sell entire position (long-only fund, no shorting)
            pos = portfolio["positions"][ticker]
            try:
                price = _get_current_price(ticker)
                if price:
                    proceeds = pos["shares"] * price
                    pnl = (price - pos["avg_cost"]) * pos["shares"]
                    portfolio["cash"] += proceeds
                    actions_taken.append(
                        f"  SELL {pos['shares']} {ticker} @ ${price:.2f} = ${proceeds:,.0f} "
                        f"(PnL: ${pnl:+,.0f})"
                    )
                    portfolio["history"].append({
                        "date": date, "action": "SELL", "ticker": ticker,
                        "shares": pos["shares"], "price": price, "pnl": pnl,
                    })
                    del portfolio["positions"][ticker]
            except Exception as e:
                print(f"  Could not sell {ticker}: {e}")

    # Record daily NAV
    nav = portfolio["cash"] + _total_position_value(portfolio)
    portfolio["daily_nav"].append({"date": date, "nav": nav})

    save_portfolio(portfolio)

    if actions_taken:
        print(f"\nActions taken on {date}:")
        print("\n".join(actions_taken))
    else:
        print("No actions taken (all signals were HOLD or positions unchanged).")

    print(f"\nPortfolio NAV: ${nav:,.0f}")
    print(f"Cash: ${portfolio['cash']:,.0f}")
    print(f"Positions: {len(portfolio['positions'])}")


def cmd_status(args):
    """Show current portfolio status."""
    portfolio = load_portfolio()
    if not portfolio:
        return

    print(f"\n{'='*60}")
    print("  CENTILLION VIRTUAL PORTFOLIO")
    print(f"{'='*60}")
    print(f"  Inception: {portfolio['inception_date']}")
    print(f"  Cash:      ${portfolio['cash']:,.0f}")

    total_mkt = 0
    total_cost = 0

    if portfolio["positions"]:
        print(f"\n  {'Ticker':<10} {'Shares':<8} {'AvgCost':<10} {'Current':<10} {'MktVal':<12} {'PnL':<12}")
        print(f"  {'-'*62}")

        for ticker, pos in sorted(portfolio["positions"].items()):
            price = _get_current_price(ticker) or pos["avg_cost"]
            mkt_val = pos["shares"] * price
            cost_basis = pos["shares"] * pos["avg_cost"]
            pnl = mkt_val - cost_basis
            total_mkt += mkt_val
            total_cost += cost_basis
            print(
                f"  {ticker:<10} {pos['shares']:<8} ${pos['avg_cost']:<9.2f} ${price:<9.2f} "
                f"${mkt_val:<11,.0f} ${pnl:<+11,.0f}"
            )

    nav = portfolio["cash"] + total_mkt
    total_return = ((nav / portfolio["initial_cash"]) - 1) * 100

    print(f"\n  Total Market Value: ${total_mkt:,.0f}")
    print(f"  Total NAV:         ${nav:,.0f}")
    print(f"  Total Return:      {total_return:+.2f}%")
    print(f"  # Positions:       {len(portfolio['positions'])}")
    print(f"{'='*60}\n")


def cmd_performance(args):
    """Show performance history and comparison to benchmarks."""
    portfolio = load_portfolio()
    if not portfolio:
        return

    if not portfolio["daily_nav"]:
        print("No NAV history yet. Run 'update' after each analysis.")
        return

    initial = portfolio["initial_cash"]
    print(f"\n  NAV History:")
    print(f"  {'Date':<12} {'NAV':<15} {'Return':<10}")
    print(f"  {'-'*37}")

    for entry in portfolio["daily_nav"]:
        ret = ((entry["nav"] / initial) - 1) * 100
        print(f"  {entry['date']:<12} ${entry['nav']:<14,.0f} {ret:+.2f}%")

    # Trade history summary
    trades = portfolio["history"]
    if trades:
        total_pnl = sum(t.get("pnl", 0) for t in trades if t["action"] == "SELL")
        wins = sum(1 for t in trades if t["action"] == "SELL" and t.get("pnl", 0) > 0)
        losses = sum(1 for t in trades if t["action"] == "SELL" and t.get("pnl", 0) <= 0)
        print(f"\n  Closed Trades: {wins + losses} (Wins: {wins}, Losses: {losses})")
        print(f"  Realized PnL:  ${total_pnl:+,.0f}")


def _get_current_price(ticker):
    """Fetch current/latest price for a ticker via yfinance."""
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


def _total_position_value(portfolio):
    """Calculate total market value of all positions."""
    total = 0
    for ticker, pos in portfolio["positions"].items():
        price = _get_current_price(ticker) or pos["avg_cost"]
        total += pos["shares"] * price
    return total


def _extract_signal(decision_text):
    text_upper = decision_text.upper() if isinstance(decision_text, str) else ""
    for signal in ["BUY", "SELL", "HOLD"]:
        if signal in text_upper:
            return signal
    return "HOLD"


def main():
    parser = argparse.ArgumentParser(description="Centillion Virtual Portfolio Tracker")
    sub = parser.add_subparsers(dest="command")

    init_p = sub.add_parser("init", help="Initialize new virtual portfolio")
    init_p.add_argument("--cash", type=float, default=1_000_000, help="Starting cash (default $1M)")

    sub.add_parser("update", help="Apply latest signals to portfolio")
    sub.add_parser("status", help="Show current portfolio")
    sub.add_parser("performance", help="Show performance history")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "performance":
        cmd_performance(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
