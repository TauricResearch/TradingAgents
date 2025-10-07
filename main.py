from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-4o-mini"  # Use a different model
config["quick_think_llm"] = "gpt-4o-mini"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds

# Configure data vendors (default uses yfinance and alpha_vantage)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: yfinance, alpha_vantage, local
    "technical_indicators": "yfinance",      # Options: yfinance, alpha_vantage, local
    "fundamental_data": "alpha_vantage",     # Options: openai, alpha_vantage, local
    "news_data": "alpha_vantage",            # Options: openai, alpha_vantage, google, local
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# Your IBKR portfolio tickers
PORTFOLIO_TICKERS = ["AVGO", "MSFT", "MU", "NVDA", "TSM"]  # Excluding SXRV (ETF)

# Analyze your largest position (AVGO - 43 shares)
print("Analyzing AVGO (Broadcom) - Your largest position...")
_, decision = ta.propagate("AVGO", "2024-10-01")
print("\n" + "="*60)
print("AVGO Analysis Result:")
print("="*60)
print(decision)

# Uncomment below to analyze all positions:
# for ticker in PORTFOLIO_TICKERS:
#     print(f"\nAnalyzing {ticker}...")
#     _, decision = ta.propagate(ticker, "2024-10-01")
#     print(f"{ticker} Decision: {decision[:200]}...")  # First 200 chars

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
