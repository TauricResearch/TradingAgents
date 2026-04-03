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
# Example for local OpenAI-compatible llama.cpp server:
# config["llm_provider"] = "ollama"
# config["backend_url"] = "http://localhost:4000/v1"

# Configure data vendors
config["data_vendors"] = {
    "core_stock_apis": "tushare,yfinance",   # Options: tushare, yfinance
    "technical_indicators": "tushare,yfinance",  # Options: tushare, yfinance
    "fundamental_data": "tushare,yfinance",  # Options: tushare, yfinance
    "news_data": "opencli,brave,yfinance",   # Options: opencli, brave, yfinance
}
config["tool_vendors"] = {
    "get_stock_data": "tushare",
    "get_indicators": "tushare",
    "get_fundamentals": "tushare",
    "get_balance_sheet": "tushare",
    "get_cashflow": "tushare",
    "get_income_statement": "tushare",
    "get_news": "opencli",
    "get_global_news": "opencli",
    "get_insider_transactions": "tushare,yfinance",
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
