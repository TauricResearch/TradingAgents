from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
import os
from dotenv import load_dotenv
load_dotenv()
config = DEFAULT_CONFIG.copy()
config["use_dapt_sentiment"] = True
config["dapt_adapter_path"] = ""  # <- set your absolute path
config["llm_provider"] = "openai"  # provider for the other agents; DAPT is used for News
config["backend_url"] = "https://api.openai.com/v1"  # unused if DAPT loads fine

graph = TradingAgentsGraph(selected_analysts=["news"], config=config, debug=True)
_, decision = graph.propagate(company_name="AAPL", trade_date="2024-01-04")
print(decision)