import functools
import time
import json
from langchain_core.messages import SystemMessage, HumanMessage

from tradingagents.log_utils import add_log, step_timer, symbol_progress


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        past_memory_str = ""
        past_memories = None
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        system_content = """You are a Trader at a financial trading desk. You MUST stay in character as a financial trader at all times.

CRITICAL RULES:
- NEVER mention that you are an AI, Claude, a language model, or an assistant
- NEVER offer to help with code, software, or implementation tasks
- NEVER say "I don't have access to" or "I can't see the data" — analyze whatever data is provided below
- If data sections are empty, state that data is unavailable and make a recommendation based on available information

Your task: Review the investment plan and market data, then provide a clear trading recommendation.

Respond with your trading analysis and conclude with: FINAL TRANSACTION PROPOSAL: **BUY**, **HOLD**, or **SELL**

RESPONSE FORMAT:
- Maximum 1500 characters. Lead with your recommendation, then key rationale.
- Complete your ENTIRE response in a SINGLE message.

Provide only your trading analysis. No disclaimers or meta-commentary."""

        user_content = f"""Company: {company_name}

Investment Plan from Analysts:
{investment_plan}

Past reflections from similar situations:
{past_memory_str}

Based on this analysis, what is your trading recommendation for {company_name}?"""

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=user_content),
        ]

        step_timer.start_step("trader")
        add_log("agent", "trader", f"💰 Trader calling LLM for {company_name}...")
        t0 = time.time()
        result = llm.invoke(messages)
        elapsed = time.time() - t0
        add_log("llm", "trader", f"LLM responded in {elapsed:.1f}s ({len(result.content)} chars)")
        add_log("agent", "trader", f"✅ Trader plan ready: {result.content[:300]}...")
        step_timer.end_step("trader", "completed", result.content[:200])
        symbol_progress.step_done(company_name, "trader")
        step_timer.set_details("trader", {
            "system_prompt": system_content,
            "user_prompt": user_content[:3000],
            "response": result.content[:3000],
            "tool_calls": [],
        })

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
