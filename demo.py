"""MiniMax + TradingAgents demo (backtest mode).

Run:
    python demo.py
"""

import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from tradingagents.agents.agent import Agent
from tradingagents.llm_clients.factory import create_llm_client


def main():
    print("=" * 60)
    print("TradingAgents — MiniMax M2.7 Demo (NVDA Backtest)")
    print("=" * 60)

    llm_provider = "minimax"
    deep_think_llm = "MiniMax-M2.7"
    quick_think_llm = "MiniMax-M2.7"

    deep_client = create_llm_client(provider=llm_provider, model=deep_think_llm)
    quick_client = create_llm_client(provider=llm_provider, model=quick_think_llm)

    print(f"\nLLM provider : {llm_provider}")
    print(f"Deep think   : {deep_think_llm}")
    print(f"Quick think  : {quick_think_llm}")

    agent = Agent(deep_think_client=deep_client, quick_think_client=quick_client)

    ticker = "NVDA"
    backtest_date = "2024-05-10"
    agent_type = "analyst"

    print(f"\nTicker       : {ticker}")
    print(f"Date         : {backtest_date}")
    print(f"Agent type   : {agent_type}")
    print("-" * 60)

    result = agent.run(ticker=ticker, agent_type=agent_type, backtest_date=backtest_date)

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    main()
