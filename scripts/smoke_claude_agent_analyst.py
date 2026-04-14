"""Shape B smoke test: run the market analyst end-to-end against a ticker/date
via the claude_agent provider, confirming MCP tool translation and the SDK-
native tool loop.

Requires the user to be logged into Claude Code.
"""

import time

from langchain_core.messages import HumanMessage

from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.llm_clients.factory import create_llm_client


def main():
    client = create_llm_client(provider="claude_agent", model="sonnet")
    llm = client.get_llm()

    node = create_market_analyst(llm)

    state = {
        "trade_date": "2025-10-15",
        "company_of_interest": "AAPL",
        "messages": [
            HumanMessage(
                content=(
                    "Produce a concise market analysis report for AAPL based on "
                    "the most recent price data and a few key technical indicators. "
                    "Keep it under 500 words."
                )
            )
        ],
    }

    print(f"Running market analyst on {state['company_of_interest']} @ {state['trade_date']}...")
    start = time.monotonic()
    output = node(state)
    elapsed = time.monotonic() - start

    report = output.get("market_report", "")
    print(f"\n--- market_report ({elapsed:.1f}s, {len(report)} chars) ---\n")
    print(report)

    assert report, "market_report is empty"
    assert "messages" in output and len(output["messages"]) == 1
    print("\nShape B smoke test OK.")


if __name__ == "__main__":
    main()
