from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "anthropic"
config["deep_think_llm"] = "claude-sonnet-4-20250514"
config["quick_think_llm"] = "claude-sonnet-4-20250514"
config["backend_url"] = "https://api.anthropic.com"
config["max_debate_rounds"] = 1  # debate rounds

# Example: OpenRouter configuration (uncomment to use)
# config["llm_provider"] = "openrouter"
# config["deep_think_llm"] = "anthropic/claude-sonnet-4.5"  # or any OpenRouter model
# config["quick_think_llm"] = "anthropic/claude-sonnet-4.5"
# config["backend_url"] = "https://openrouter.ai/api/v1"
# Note: Set OPENROUTER_API_KEY in .env file
# Note: For embeddings, also set OPENAI_API_KEY (OpenRouter doesn't provide embeddings)

# Configure data vendors (default uses yfinance and alpha_vantage)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: yfinance, alpha_vantage, local
    "technical_indicators": "yfinance",      # Options: yfinance, alpha_vantage, local
    "fundamental_data": "yfinance",          # Options: openai, alpha_vantage, yfinance, local
    "news_data": "google",                   # Options: openai, alpha_vantage, google, local
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
