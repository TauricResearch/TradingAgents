"""
run_ollama.py — Quick-start TradingAgents with local Ollama and free yfinance data.

Available local models (from http://localhost:11434):
    - gemma4:26b      (25.8B  — best reasoning, recommended default)
  - gpt-oss:20b     (20.9B  — good reasoning)
    - gemma4:e2b      (5.1B   — fast, lower-quality option)
  - gemma3n:latest  (6.9B)
  - mistral:7b      (7.2B)
  - llama3.2:latest (3.2B   — fastest)

Usage:
    .\.venv\Scripts\python run_ollama.py
    .\.venv\Scripts\python run_ollama.py --ticker AAPL --date 2025-01-15
"""

import argparse
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

OLLAMA_BASE_URL = "http://localhost:11434/v1"

# Choose models from what is available locally in Ollama.
# Adjust these to your preference.
DEEP_THINK_MODEL  = "gemma4:26b"   # large model for complex reasoning
QUICK_THINK_MODEL = "gemma4:26b"   # quality-first default for better decisions


def build_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"]    = "ollama"
    config["backend_url"]     = OLLAMA_BASE_URL
    config["deep_think_llm"]  = DEEP_THINK_MODEL
    config["quick_think_llm"] = QUICK_THINK_MODEL
    config["max_debate_rounds"]       = 1
    config["max_risk_discuss_rounds"] = 1
    # All data from yfinance (free, no API key needed)
    config["data_vendors"] = {
        "core_stock_apis":      "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data":     "yfinance",
        "news_data":            "yfinance",
    }
    return config


def main():
    parser = argparse.ArgumentParser(description="TradingAgents — Ollama + yfinance")
    parser.add_argument("--ticker", default="NVDA", help="Stock ticker (default: NVDA)")
    parser.add_argument("--date",   default="2025-01-15", help="Analysis date YYYY-MM-DD (default: 2025-01-15)")
    parser.add_argument("--debug",  action="store_true", help="Enable debug output")
    args = parser.parse_args()

    config = build_config()
    print(f"\nTradingAgents — Ollama @ {OLLAMA_BASE_URL}")
    print(f"  Deep-think model : {DEEP_THINK_MODEL}")
    print(f"  Quick-think model: {QUICK_THINK_MODEL}")
    print(f"  Ticker           : {args.ticker}")
    print(f"  Date             : {args.date}")
    print(f"  Data source      : yfinance (free)\n")

    ta = TradingAgentsGraph(debug=args.debug, config=config)
    _, decision = ta.propagate(args.ticker, args.date)
    print("\n=== TRADING DECISION ===")
    print(decision)


if __name__ == "__main__":
    main()
