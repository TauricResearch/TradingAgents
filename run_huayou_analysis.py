"""Full multi-agent analysis of 华友钴业 (603799.SH) using DeepSeek + akshare.

Usage:
    1. Fill in DEEPSEEK_API_KEY in /Users/xmye/TradingAgents/.env
    2. cd /Users/xmye/TradingAgents
    3. conda activate tradingagents
    4. python run_huayou_analysis.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Verify API key
api_key = os.environ.get("DEEPSEEK_API_KEY", "")
if not api_key or api_key.startswith("sk-your"):
    print("ERROR: Please fill in DEEPSEEK_API_KEY in .env file first!")
    print(f"  File: {os.path.join(os.path.dirname(__file__), '.env')}")
    sys.exit(1)

print(f"DeepSeek API key loaded ({api_key[:8]}...)")

# Configure for A-share + DeepSeek
from tradingagents.default_config import DEFAULT_CONFIG
from copy import deepcopy

config = deepcopy(DEFAULT_CONFIG)

# LLM config
config["llm_provider"] = "deepseek"
config["deep_think_llm"] = "deepseek-chat"      # DeepSeek V3 for complex reasoning
config["quick_think_llm"] = "deepseek-chat"      # Same for quick tasks

# Data vendor config
config["data_vendors"] = {
    "core_stock_apis": "akshare",
    "technical_indicators": "akshare",
    "fundamental_data": "akshare",
    "news_data": "akshare",
}

# Output config
config["output_language"] = "Chinese"
config["max_debate_rounds"] = 1      # 1 round for faster execution
config["max_risk_discuss_rounds"] = 1

print("\nConfig:")
print(f"  LLM: {config['llm_provider']} / {config['deep_think_llm']}")
print(f"  Data: akshare (East Money)")
print(f"  Output: Chinese")
print(f"  Debate rounds: {config['max_debate_rounds']}")

# Run analysis
print("\n" + "="*60)
print("Starting multi-agent analysis of 华友钴业 (603799.SH)...")
print("="*60 + "\n")

from tradingagents.graph.trading_graph import TradingAgentsGraph

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("603799", "2026-05-16")

print("\n" + "="*60)
print("FINAL DECISION — 华友钴业 (603799.SH)")
print("="*60)
print(decision)
print("="*60)
