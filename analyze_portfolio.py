#!/usr/bin/env python3
"""Analyze your IBKR portfolio positions"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv
from datetime import datetime, timedelta
import time

# Load environment variables
load_dotenv()

# Your IBKR positions
PORTFOLIO = [
    {"ticker": "AVGO", "name": "Broadcom Inc", "shares": 43},
    {"ticker": "MSFT", "name": "Microsoft Corp", "shares": 12},
    {"ticker": "MU", "name": "Micron Technology Inc", "shares": 13},
    {"ticker": "NVDA", "name": "Nvidia Corp", "shares": 30},
    {"ticker": "SXRV", "name": "iShares NASDAQ 100 USD ACC", "shares": 9},
    {"ticker": "TSM", "name": "Taiwan Semiconductor SP ADR", "shares": 15},
]

print("=" * 70)
print("🏦 IBKR Portfolio Analysis - TradingAgents")
print("=" * 70)
print("\nYour positions:")
for pos in PORTFOLIO:
    print(f"  • {pos['ticker']:6s} - {pos['shares']:3d} shares - {pos['name']}")

# Configure for efficient analysis
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-4o-mini"  # Use faster model for bulk analysis
config["quick_think_llm"] = "gpt-4o-mini"
config["max_debate_rounds"] = 1  # Keep it fast

# Configure data sources
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "alpha_vantage",
    "news_data": "alpha_vantage",
}

# Use recent date for analysis
analysis_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

print(f"\n📅 Analysis date: {analysis_date}")
print("🤖 Using: gpt-4o-mini (fast mode)")
print("📊 Data sources: yfinance + Alpha Vantage")
print("\n" + "=" * 70)

# Initialize the trading graph
ta = TradingAgentsGraph(debug=False, config=config)

# Store decisions
decisions = {}

# Analyze each position
for i, position in enumerate(PORTFOLIO, 1):
    ticker = position["ticker"]

    # Skip ETF for now (SXRV might not have all data available)
    if ticker == "SXRV":
        print(f"\n[{i}/6] Skipping {ticker} (ETF - limited data)")
        decisions[ticker] = "ETF - Manual review recommended"
        continue

    print(f"\n[{i}/6] Analyzing {ticker} ({position['name']})...")
    print("      🔄 Agents working...")

    try:
        start_time = time.time()
        _, decision = ta.propagate(ticker, analysis_date)
        elapsed = time.time() - start_time

        decisions[ticker] = decision
        print(f"      ✅ Complete ({elapsed:.1f}s)")

        # Brief pause to avoid rate limits
        if i < len(PORTFOLIO):
            time.sleep(2)

    except Exception as e:
        print(f"      ❌ Error: {str(e)[:100]}")
        decisions[ticker] = f"Error during analysis: {str(e)[:100]}"

# Summary Report
print("\n" + "=" * 70)
print("📈 PORTFOLIO ANALYSIS SUMMARY")
print("=" * 70)

for position in PORTFOLIO:
    ticker = position["ticker"]
    print(f"\n{'='*70}")
    print(f"📊 {ticker} - {position['name']} ({position['shares']} shares)")
    print(f"{'='*70}")

    if ticker in decisions:
        print(decisions[ticker])

print("\n" + "=" * 70)
print("✅ Portfolio analysis complete!")
print("\nNote: This is AI analysis for research purposes only.")
print("Always do your own due diligence before making trading decisions.")
print("=" * 70)