import logging

from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

load_dotenv()

# Show Claude prompts in the console
logging.basicConfig(format="%(message)s", level=logging.WARNING)
logging.getLogger("tradingagents.llm_clients").setLevel(logging.INFO)

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "claude-opus-4-6"
config["quick_think_llm"] = "claude-sonnet-4-6"
config["max_debate_rounds"] = 1

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# Propagate using a Binance crypto pair
_, decision = ta.propagate("BTCUSDT", "2024-05-10")
print(decision)
