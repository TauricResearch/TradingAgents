from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5.4-mini"  # Use a different model
config["quick_think_llm"] = "gpt-5.4-mini"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds

# Configure data vendors (default uses yfinance, no extra API keys needed)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: alpha_vantage, yfinance
    "technical_indicators": "yfinance",      # Options: alpha_vantage, yfinance
    "fundamental_data": "yfinance",          # Options: alpha_vantage, yfinance
    "news_data": "yfinance",                 # Options: alpha_vantage, yfinance
}

# Enable memory persistence so lessons survive restarts (optional).
# Set to None or omit to keep the default RAM-only behaviour.
config["memory_persist_dir"] = "~/.tradingagents/memory"

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# Reflect on the decision after observing actual returns.
# Call this once the position closes and the P&L is known.
# The signed float indicates outcome: positive = correct signal,
# negative = incorrect signal.  Lessons are persisted when
# memory_persist_dir is set, so the next TradingAgentsGraph
# instance will load them automatically.
# ta.reflect_and_remember(0.03)  # e.g. 3 % gain
