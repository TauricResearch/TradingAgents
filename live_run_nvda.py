import asyncio
import os
import sys

# Ensure we can import from the project root
sys.path.append(os.getcwd())

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


async def run_live():
    # Configure for OpenRouter
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "openrouter"
    config["quick_think_llm"] = "openai/gpt-4o-mini"
    config["mid_think_llm"] = "openai/gpt-4o-mini"
    config["deep_think_llm"] = "openai/gpt-4o-mini"

    # Use YFinance for data (usually doesn't need keys for basic stuff)
    config["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
        "scanner_data": "yfinance",
        "calendar_data": "finnhub",
    }

    # Reduce rounds for faster test
    config["max_debate_rounds"] = 1

    ticker = "NVDA"
    trade_date = "2024-05-10"  # Use a past date for better data availability

    print(f"--- Starting Live Run for {ticker} on {trade_date} ---")
    print(f"Using Provider: {config['llm_provider']}")
    print(f"Using Model: {config['quick_think_llm']}")

    # Initialize Graph
    # We'll use just a few analysts to keep it focused
    ta = TradingAgentsGraph(selected_analysts=["market", "fundamentals"], debug=True, config=config)

    try:
        # Run propagation
        final_state, signal = ta.propagate(ticker, trade_date)

        print("\n--- Run Completed ---")
        print(f"Final Decision Signal: {signal}")

        # Monitor propagation
        print("\n--- Information Propagation Analysis ---")

        # 1. Market Report -> Research Manager
        market_report = final_state.get("market_report", "")
        print(f"Market Report generated: {len(market_report)} chars")

        # 2. Fundamentals Report -> Research Manager
        fundamentals_report = final_state.get("fundamentals_report", "")
        print(f"Fundamentals Report generated: {len(fundamentals_report)} chars")

        # 3. Investment Plan (Research Manager output)
        investment_plan = final_state.get("investment_plan", "")
        print(f"Investment Plan (RM): {len(investment_plan)} chars")

        # 4. Trader Plan
        trader_plan = final_state.get("trader_investment_plan", "")
        print(f"Trader Plan: {len(trader_plan)} chars")

        # 5. Final Decision
        final_decision = final_state.get("final_trade_decision", "")
        print(f"Final Portfolio Manager Decision: {len(final_decision)} chars")

        # Check if structured data propagated
        market_struct = final_state.get("market_report_structured", {})
        print(f"Market Structured Status: {market_struct.get('status')}")
        print(f"Market Macro Regime: {market_struct.get('macro_regime')}")

        rm_struct = final_state.get("investment_plan_structured", {})
        print(f"RM Recommendation: {rm_struct.get('recommendation')}")

        pm_struct = final_state.get("final_trade_decision_structured", {})
        print(f"PM Final Action: {pm_struct.get('action')}")

        # Path to logs
        from tradingagents.report_paths import get_eval_dir

        run_id = final_state.get("run_id")
        eval_dir = get_eval_dir(trade_date, ticker, run_id)
        print(f"\nFull logs saved to: {eval_dir}")

    except Exception as e:
        print(f"Error during live run: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_live())
