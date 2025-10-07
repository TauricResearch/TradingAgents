#!/usr/bin/env python3
"""Quick demo of TradingAgents analyzing a stock"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv
import datetime

# Load environment variables
load_dotenv()

print("=" * 60)
print("🚀 TradingAgents Quick Demo")
print("=" * 60)

# Configure for fast testing
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-4o-mini"  # Use faster model
config["quick_think_llm"] = "gpt-4o-mini"  # Use faster model
config["max_debate_rounds"] = 1  # Reduce debate rounds for speed

# Configure data sources
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "alpha_vantage",
    "news_data": "alpha_vantage",
}

print("\n📊 Analyzing NVDA stock for 2024-05-10...")
print("   Using: gpt-4o-mini (fast mode)")
print("   Data: yfinance + Alpha Vantage")
print("\n🔄 This will take 1-2 minutes as agents analyze the data...\n")

# Initialize the trading graph
ta = TradingAgentsGraph(debug=True, config=config)

# Run analysis
try:
    _, decision = ta.propagate("NVDA", "2024-05-10")

    print("\n" + "=" * 60)
    print("📈 TRADING DECISION")
    print("=" * 60)
    print(decision)

except Exception as e:
    print(f"\n❌ Error during analysis: {e}")
    print("\nThis might happen if:")
    print("- API rate limits are reached")
    print("- Network connectivity issues")
    print("- Invalid API keys")

print("\n✅ Demo complete!")