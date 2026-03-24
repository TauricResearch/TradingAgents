"""Portfolio analysis example.

Analyzes multiple stocks in a portfolio and produces a comparative
recommendation for each position (KEEP / REDUCE / EXIT).

Related GitHub issues: #60, #406
"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

load_dotenv()

config = DEFAULT_CONFIG.copy()
# Customize LLM provider and models as needed:
# config["llm_provider"] = "anthropic"  # or "openai", "google"
# config["deep_think_llm"] = "claude-sonnet-4-20250514"
# config["quick_think_llm"] = "claude-haiku-4-5-20251001"
config["max_debate_rounds"] = 1

ta = TradingAgentsGraph(debug=False, config=config)

# Define your portfolio
portfolio = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN"]

# Run the portfolio analysis
results = ta.propagate_portfolio(portfolio, "2025-03-23")

# Print individual signals
print("\n=== INDIVIDUAL SIGNALS ===")
for ticker, result in results["individual_results"].items():
    print(f"  {ticker}: {result['signal']}")

# Print the comparative portfolio summary
print("\n=== PORTFOLIO SUMMARY ===")
print(results["portfolio_summary"])
