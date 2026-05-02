#!/usr/bin/env python3
"""Run a TradingAgents analysis from CLI args."""
import argparse
import datetime
from dotenv import load_dotenv
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

def main():
    parser = argparse.ArgumentParser(description="Run TradingAgents analysis")
    parser.add_argument("ticker", help="Ticker symbol (e.g. TKA.DE)")
    parser.add_argument("--date", default="today", help="Analysis date (YYYY-MM-DD or 'today')")
    parser.add_argument("--debates", type=int, default=1, help="Number of debate rounds")
    parser.add_argument("--analysts", default="market,news,fundamentals",
                        help="Comma-separated analyst types")
    args = parser.parse_args()

    load_dotenv()

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "openrouter"
    config["deep_think_llm"] = "openai/gpt-5.4"
    config["quick_think_llm"] = "openai/gpt-5.4-mini"
    config["max_debate_rounds"] = args.debates
    config["max_risk_discuss_rounds"] = args.debates

    analysts = [a.strip() for a in args.analysts.split(",")]

    if args.date == "today":
        args.date = datetime.date.today().isoformat()

    graph = TradingAgentsGraph(analysts, config=config, debug=True)
    _, decision = graph.propagate(args.ticker, args.date)
    print(decision)

if __name__ == "__main__":
    main()
