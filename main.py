import os

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()

# LLM overrides from .env (fall back to DEFAULT_CONFIG when unset)
if os.getenv("LLM_PROVIDER"):
    config["llm_provider"] = os.getenv("LLM_PROVIDER")
if os.getenv("DEEP_THINK_LLM"):
    config["deep_think_llm"] = os.getenv("DEEP_THINK_LLM")
if os.getenv("QUICK_THINK_LLM"):
    config["quick_think_llm"] = os.getenv("QUICK_THINK_LLM")
if os.getenv("LLM_BACKEND_URL"):
    config["backend_url"] = os.getenv("LLM_BACKEND_URL")

config["max_debate_rounds"] = 1  # Increase debate rounds

# Configure data vendors (default uses yfinance, no extra API keys needed)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: alpha_vantage, yfinance
    "technical_indicators": "yfinance",      # Options: alpha_vantage, yfinance
    "fundamental_data": "yfinance",          # Options: alpha_vantage, yfinance
    "news_data": "yfinance",                 # Options: alpha_vantage, yfinance
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
