from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.config import get_config, update_config

# Get the centralized config (already includes .env loading)
config = get_config()

# Customize config if needed
updates = {
    "deep_think_llm": "gpt-4o-mini",  # Use a different model
    "quick_think_llm": "gpt-4o-mini",  # Use a different model
    "max_debate_rounds": 1,  # Increase debate rounds
    # Configure data vendors
    "data_vendors": {
        "core_stock_apis": "yfinance",           # Options: yfinance, alpha_vantage, local
        "technical_indicators": "yfinance",      # Options: yfinance, alpha_vantage, local
        "fundamental_data": "alpha_vantage",     # Options: openai, alpha_vantage, local
        "news_data": "alpha_vantage",            # Options: openai, alpha_vantage, google, local
    }
}
update_config(updates)

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=get_config())

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
