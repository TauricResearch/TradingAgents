"""
Playground: Run only the Fundamentals Analyst on a given ticker + date.

Usage:
    uv run python playground/play_fundamentals.py
"""

from dotenv import load_dotenv

load_dotenv()

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.config import set_config
from tradingagents.llm_clients import create_llm_client
from tradingagents.agents import create_fundamentals_analyst

# ── Config ────────────────────────────────────────────────
TICKER = "NVDA"
TRADE_DATE = "2026-02-29"

config = DEFAULT_CONFIG.copy()
# Uncomment / edit to switch providers:
# config["llm_provider"] = "openai"
# config["quick_think_llm"] = "gpt-4o-mini"

# Initialize the global dataflows config (needed by tools)
set_config(config)

# ── Create LLM ────────────────────────────────────────────
llm_kwargs = {}
if config["llm_provider"] == "google":
    llm_kwargs["thinking_level"] = config.get("google_thinking_level")
elif config["llm_provider"] == "openai":
    llm_kwargs["reasoning_effort"] = config.get("openai_reasoning_effort")
elif config["llm_provider"] == "anthropic":
    llm_kwargs["effort"] = config.get("anthropic_effort")

client = create_llm_client(
    provider=config["llm_provider"],
    model=config["quick_think_llm"],
    base_url=config.get("backend_url"),
    **llm_kwargs,
)
llm = client.get_llm()

# ── Build the analyst node function ───────────────────────
fundamentals_node = create_fundamentals_analyst(llm)

# ── Simulate the AgentState that the graph would pass in ──
from langchain_core.messages import HumanMessage

state = {
    "messages": [HumanMessage(content=f"Analyze {TICKER}")],
    "company_of_interest": TICKER,
    "trade_date": TRADE_DATE,
}

# ── Run the analyst (may need multiple loops for tool calls) ──
from langgraph.prebuilt import ToolNode
from tradingagents.agents.utils.agent_utils import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
)

tools = [get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement]
tool_node = ToolNode(tools)

MAX_ITERATIONS = 3


if __name__ == "__main__":
    for i in range(MAX_ITERATIONS):
        print(f"\n{'='*60}")
        print(f"Iteration {i + 1}")
        print(f"{'='*60}")

        result = fundamentals_node(state)

        # Update messages in state
        state["messages"] = state["messages"] + result["messages"]

        last_msg = result["messages"][-1]

        # Check if the analyst made tool calls
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            print(f"  Tool calls: {[tc['name'] for tc in last_msg.tool_calls]}")
            # Execute the tools and feed results back
            tool_result = tool_node.invoke({"messages": state["messages"]})
            state["messages"] = state["messages"] + tool_result["messages"]
        else:
            # No more tool calls — we have the final report
            print("\n✅ Fundamentals report ready!\n")
            print(result.get("fundamentals_report", last_msg.content))
            break
    else:
        print("⚠️  Hit max iterations")
