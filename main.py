from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5-mini"  # Use a different model
config["quick_think_llm"] = "gpt-5-mini"  # Use a different model
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

# --- Run 1: forward propagate ---
_, decision = ta.propagate("NVDA", "2024-05-10")
print("Decision:", decision)

# --- Self-learning: reflect on the outcome and update agent memories ---
# Pass the realized profit/loss from the trade (positive = profit, negative = loss).
# Each agent (Bull Researcher, Bear Researcher, Trader, Investment Judge,
# Portfolio Manager) will analyse its own reasoning against the actual outcome,
# extract actionable lessons, and store them in its BM25 memory so that future
# decisions on similar market conditions are informed by past experience.
#
# Uncomment and adjust the P&L value to enable the self-learning cycle:
# ta.reflect_and_remember(1000)  # e.g. position returned +$1 000
