"""
Example: Using TradingAgents with Ollama (Local AI)

This demonstrates how to use TradingAgents with Ollama instead of OpenAI.
Ollama allows you to run AI models locally and for FREE!
"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
import os

# Set Alpha Vantage API key (still needed for financial data)
# You can get a free key at: https://www.alphavantage.co/support/#api-key
if not os.getenv("ALPHA_VANTAGE_API_KEY"):
    print("⚠️  Warning: ALPHA_VANTAGE_API_KEY not set!")
    print("   Get a free key at: https://www.alphavantage.co/support/#api-key")
    print("   export ALPHA_VANTAGE_API_KEY=your-key-here")
    print()

print("="*60)
print("TradingAgents with Ollama (Local AI)")
print("="*60)
print()

# Create Ollama configuration
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "llama3"  # Use llama3 for complex reasoning
config["quick_think_llm"] = "llama3"  # Use llama3 for quick tasks
config["backend_url"] = "http://localhost:11434"
config["temperature"] = 0.7

print("Configuration:")
print(f"  Provider: {config['llm_provider']}")
print(f"  Deep Think Model: {config['deep_think_llm']}")
print(f"  Quick Think Model: {config['quick_think_llm']}")
print(f"  Endpoint: {config['backend_url']}")
print()

# You can also configure which analysts to use
selected_analysts = ["market"]  # Start with just market analyst for faster testing
# Full options: ["market", "social", "news", "fundamentals"]

print("Creating TradingAgentsGraph...")
ta = TradingAgentsGraph(
    config=config,
    debug=True,
    selected_analysts=selected_analysts
)
print("✅ TradingAgentsGraph created successfully!")
print()

# Test with a simple stock analysis
ticker = "AAPL"  # Apple Inc.
date = "2024-05-10"

print(f"Analyzing {ticker} on {date}...")
print("This may take a few minutes with local models...")
print()

try:
    state, decision = ta.propagate(ticker, date)
    
    print("="*60)
    print("ANALYSIS COMPLETE!")
    print("="*60)
    print()
    print(f"Decision: {decision}")
    print()
    
    # Show some of the analysis
    if "market_analyst_report" in state:
        print("Market Analyst Report (excerpt):")
        report = state["market_analyst_report"]
        print(report[:500] + "..." if len(report) > 500 else report)
        print()
    
except Exception as e:
    print(f"❌ Error during analysis: {e}")
    import traceback
    traceback.print_exc()
    print()
    print("Troubleshooting tips:")
    print("1. Make sure Ollama is running: ollama serve")
    print("2. Make sure llama3 is installed: ollama pull llama3")
    print("3. Set ALPHA_VANTAGE_API_KEY environment variable")

print()
print("="*60)
print("Done!")
print("="*60)
print()
print("💡 Tips:")
print("  - Use more analysts for comprehensive analysis:")
print("    selected_analysts=['market', 'news', 'fundamentals']")
print("  - Ollama is FREE and runs locally!")
print("  - Try different models: mistral, mixtral, etc.")
print("  - For faster analysis, use smaller models")
