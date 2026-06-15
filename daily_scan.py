"""
Daily watchlist scanner for a $70k eToro active sleeve.

Run each morning before market open (8:00–9:30 AM ET):
    python daily_scan.py

To scan a single ticker for deeper analysis:
    python daily_scan.py NVDA

Results are saved to ~/.tradingagents/logs/ as full markdown reports.
"""

import sys
import json
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

# ---------------------------------------------------------------------------
# Portfolio configuration
# ---------------------------------------------------------------------------

# Active sleeve size (adjust if you rebalance)
ACTIVE_SLEEVE = 35_000

# Standard position sizes
POSITION_STANDARD = 3_500     # typical position
POSITION_HIGH_CONVICTION = 5_000   # Buy signal with strong debate
POSITION_STARTER = 2_000      # Overweight — build slowly
POSITION_MAX = 6_000          # hard cap per position

# Full personal watchlist (25 tickers across US, EU, HK, and crypto)
WATCHLIST_ALL = [
    # US stocks
    "TSLA", "FSLR", "QCOM", "ADBE", "C",
    "MET", "MRK", "PLAB", "HRMY", "PBF", "ET", "BABA",
    # US ETFs & commodities
    "SPY", "DIA", "HDV", "GLD",
    # European-listed ETFs (XETRA & LSE)
    "TRET.DE", "SXR8.DE", "IDEM.L", "CNDX.L", "IJPE.L",
    # Hong Kong-listed
    "9618.HK", "1211.HK",
    # Crypto
    "BTC-USD", "ETH-USD",
]

# 5-group thematic rotation — 5 tickers per day keeps cost and runtime manageable
# Override at runtime: python daily_scan.py TSLA QCOM
DAILY_ROTATION = {
    0: ["TSLA", "FSLR", "QCOM", "ADBE", "C"],           # Monday   — US growth & tech
    1: ["SPY", "DIA", "HDV", "GLD", "MET"],              # Tuesday  — US ETFs & commodities
    2: ["PBF", "ET", "MRK", "PLAB", "HRMY"],             # Wednesday— US energy, pharma, small-cap
    3: ["TRET.DE", "SXR8.DE", "IDEM.L", "IJPE.L", "CNDX.L"],  # Thursday — European/UK ETFs
    4: ["BTC-USD", "ETH-USD", "9618.HK", "1211.HK", "BABA"],   # Friday   — Crypto, HK & China
}

# ---------------------------------------------------------------------------
# Signal → action mapping
# ---------------------------------------------------------------------------

SIGNAL_ACTIONS = {
    "Buy":         ("BUY",        f"Open/add position — target ${POSITION_HIGH_CONVICTION:,}"),
    "Overweight":  ("ADD",        f"Add starter position — target ${POSITION_STARTER:,}"),
    "Hold":        ("HOLD",       "No action — keep existing position"),
    "Underweight": ("TRIM",       "Reduce position by ~50%"),
    "Sell":        ("SELL",       "Close position entirely"),
}

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

SIGNAL_ICONS = {
    "Buy": "▲▲",
    "Overweight": "▲",
    "Hold": "━━",
    "Underweight": "▼",
    "Sell": "▼▼",
}

def print_header(text: str):
    width = 64
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)

def print_signal_row(ticker: str, signal: str, error: str | None = None):
    if error:
        print(f"  {'✗':2s}  {ticker:<8s}  ERROR — {error}")
        return
    icon = SIGNAL_ICONS.get(signal, "?")
    action, guidance = SIGNAL_ACTIONS.get(signal, ("?", "Unknown signal"))
    print(f"  {icon}  {ticker:<8s}  {signal:<12s}  →  {action:<6s}  {guidance}")

def save_summary(results: dict, today: str, log_dir: Path):
    summary_path = log_dir / f"daily_summary_{today}.json"
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump({
            "date": today,
            "generated_at": datetime.now().isoformat(),
            "results": results,
            "portfolio": {
                "active_sleeve": ACTIVE_SLEEVE,
                "position_standard": POSITION_STANDARD,
                "position_high_conviction": POSITION_HIGH_CONVICTION,
            },
        }, f, indent=2)
    return summary_path

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    today = str(date.today())
    weekday = date.today().weekday()

    # Determine which tickers to scan
    if len(sys.argv) > 1:
        tickers = [t.upper() for t in sys.argv[1:]]
        print(f"Running targeted analysis: {', '.join(tickers)}")
    else:
        tickers = DAILY_ROTATION.get(weekday, WATCHLIST_ALL[:4])
        day_name = date.today().strftime("%A")
        print(f"Running {day_name} rotation: {', '.join(tickers)}")

    print_header(f"TradingAgents Daily Scan — {today}")
    print(f"  Active sleeve: ${ACTIVE_SLEEVE:,}  |  Tickers: {len(tickers)}")
    print(f"  Reports saved to: ~/.tradingagents/logs/\n")

    # Build config (env vars already applied via DEFAULT_CONFIG)
    config = DEFAULT_CONFIG.copy()
    config["news_article_limit"] = 15
    config["global_news_article_limit"] = 5

    ta = TradingAgentsGraph(debug=False, config=config)

    results = {}
    errors = {}

    for ticker in tickers:
        print(f"\n--- Analysing {ticker} ({tickers.index(ticker)+1}/{len(tickers)}) ---")
        try:
            _, decision = ta.propagate(ticker, today)
            results[ticker] = decision
            print(f"  Signal: {decision}")
        except Exception as exc:
            errors[ticker] = str(exc)
            print(f"  ERROR: {exc}")

    # Summary table
    print_header("Signal Summary")
    for ticker in tickers:
        if ticker in results:
            print_signal_row(ticker, results[ticker])
        else:
            print_signal_row(ticker, "", error=errors.get(ticker, "unknown"))

    # Position sizing guidance
    buys = [t for t, s in results.items() if s == "Buy"]
    overweights = [t for t, s in results.items() if s == "Overweight"]
    sells = [t for t, s in results.items() if s in ("Sell", "Underweight")]

    if buys or overweights or sells:
        print_header("Today's Action Plan")
        total_deploy = 0
        for t in buys:
            size = POSITION_HIGH_CONVICTION
            total_deploy += size
            print(f"  BUY   {t:<6s}  Open/add position   ≈ ${size:,}")
        for t in overweights:
            size = POSITION_STARTER
            total_deploy += size
            print(f"  ADD   {t:<6s}  Starter position    ≈ ${size:,}")
        for t in sells:
            sig = results[t]
            action = "Close" if sig == "Sell" else "Trim 50%"
            print(f"  EXIT  {t:<6s}  {action}")
        if total_deploy:
            print(f"\n  Capital to deploy today: ~${total_deploy:,}")
            print(f"  Remember: set stop-loss at -8% on every new position")
            print(f"  Check eToro earnings calendar before opening any position")

    # Save JSON summary
    log_dir = Path.home() / ".tradingagents" / "logs"
    summary_path = save_summary(results, today, log_dir)
    print(f"\n  Full reports: {log_dir}/")
    print(f"  Summary JSON: {summary_path}")

    print_header("Done")
    print("  Review full markdown reports before executing any trade.")
    print("  Memory log (past decisions): ~/.tradingagents/memory/trading_memory.md\n")

if __name__ == "__main__":
    main()
