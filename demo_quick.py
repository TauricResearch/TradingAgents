"""Quick demo script for TradingAgents"""
import os
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Quick config
config = DEFAULT_CONFIG.copy()
config["max_debate_rounds"] = 1  # Quick demo

print("🚀 TradingAgents Demo")
print("=" * 60)
print(f"📊 Analyzing: NVDA (NVIDIA)")
print(f"📅 Date: 2024-05-10")
print(f"🤖 Provider: {config['llm_provider']}")
print(f"🧠 Deep Think: {config['deep_think_llm']}")
print(f"⚡ Quick Think: {config['quick_think_llm']}")
print("=" * 60)

try:
    # Initialize
    ta = TradingAgentsGraph(debug=True, config=config)
    
    # Run analysis
    print("\n🔄 Starting analysis...\n")
    _, decision = ta.propagate("NVDA", "2024-05-10")
    
    print("\n" + "=" * 60)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 60)
    print(decision)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\n💡 Make sure:")
    print("   1. Google API keys are set in .env")
    print("   2. Virtual environment is activated")
    print("   3. All dependencies are installed")
