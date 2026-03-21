from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing any
# tradingagents modules so TRADINGAGENTS_* vars are visible to
# DEFAULT_CONFIG at import time.
load_dotenv()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5-mini"  # Use a different model
config["quick_think_llm"] = "gpt-5-mini"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds

# Configure data vendors (default uses yfinance, no extra API keys needed)
config["data_vendors"] = {
    "core_stock_apis": "alpha_vantage",           # Options: alpha_vantage, yfinance
    "technical_indicators": "alpha_vantage",      # Options: alpha_vantage, yfinance
    "fundamental_data": "alpha_vantage",          # Options: alpha_vantage, yfinance
    "news_data": "alpha_vantage",                 # Options: alpha_vantage, yfinance
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# Memorize mistakes and reflect
ta.reflect_and_remember(1000) # parameter is the position returns
