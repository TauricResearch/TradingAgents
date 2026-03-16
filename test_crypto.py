from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv
import os

load_dotenv()
os.environ["OPENAI_API_KEY"] = "not-needed"

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["deep_think_llm"] = "claude-sonnet-4"
config["quick_think_llm"] = "claude-sonnet-4"
config["backend_url"] = "http://localhost:3456/v1"
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1

ta = TradingAgentsGraph(debug=True, config=config)

_, decision = ta.propagate("BTC-USD", "2026-03-14")
print("\n" + "="*60)
print("TRADING DECISION:")
print("="*60)
print(decision)
