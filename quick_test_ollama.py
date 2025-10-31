"""
Quick test to verify Ollama works with TradingAgents analysts.
This is a minimal test that should complete quickly.
"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
import os

print("="*60)
print("Quick Ollama Test with Market Analyst")
print("="*60)
print()

# Make sure we have Alpha Vantage key
if not os.getenv("ALPHA_VANTAGE_API_KEY"):
    print("⚠️  Setting dummy Alpha Vantage key for testing...")
    os.environ["ALPHA_VANTAGE_API_KEY"] = "demo"

# Configure for Ollama
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "llama3.2"  # llama3.2 supports tool calling
config["quick_think_llm"] = "llama3.2"  # llama3.2 supports tool calling
config["backend_url"] = "http://localhost:11434"

print("Configuration:")
print(f"  Provider: {config['llm_provider']}")
print(f"  Model: {config['quick_think_llm']}")
print()

# Create graph with just market analyst for quick test
print("Creating TradingAgentsGraph with market analyst only...")
ta = TradingAgentsGraph(
    config=config,
    debug=True,
    selected_analysts=["market"]  # Just market analyst for speed
)
print("✅ Graph created!")
print()

print("Testing with AAPL on 2024-05-10...")
print("This will test if Ollama can handle tool binding...")
print()

try:
    state, decision = ta.propagate("AAPL", "2024-05-10")
    print()
    print("="*60)
    print("✅ SUCCESS! Ollama works with TradingAgents!")
    print("="*60)
    print(f"\nDecision: {decision}")
    
except Exception as e:
    print()
    print("="*60)
    print("❌ Error occurred")
    print("="*60)
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()
