"""Full TradingAgents run using a Claude Max subscription (no API key).

Requires being logged into Claude Code. Start small: one analyst, one debate
round. The analyst tool loop takes ~1-2 min/analyst via the SDK, so a full
4-analyst run will be ~10 min end-to-end.
"""

from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

load_dotenv()

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "claude_agent"
config["deep_think_llm"] = "sonnet"   # or "opus" for slower / higher quality
config["quick_think_llm"] = "sonnet"
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1

# YFinance — no API key needed.
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
}

ta = TradingAgentsGraph(
    # Start with one analyst to validate the pipeline before burning minutes
    # on the full set. Expand to ["market", "social", "news", "fundamentals"]
    # once this works.
    selected_analysts=["market"],
    debug=True,
    config=config,
)

_, decision = ta.propagate("NVDA", "2025-10-15")
print("\n=== DECISION ===")
print(decision)
