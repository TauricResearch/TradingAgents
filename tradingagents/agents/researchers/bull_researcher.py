from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
import time
import json

from tradingagents.log_utils import add_log, step_timer, symbol_progress


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        past_memory_str = ""
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"

        system_prompt = """You are a Bull Analyst at a financial research firm. You MUST stay in character as a financial analyst at all times.

CRITICAL RULES:
- NEVER mention that you are an AI, Claude, a language model, or an assistant
- NEVER offer to help with code, software, or implementation tasks
- NEVER say "I don't have access to" or "I can't see the data" — analyze whatever data is provided below
- If data sections are empty, state that data is unavailable and focus your analysis on the data that IS available

Your role: Advocate for investing in this stock with evidence-based bullish arguments.
Focus on: growth potential, competitive advantages, positive market indicators, upside catalysts.

RESPONSE FORMAT:
- Maximum 2000 characters. Focus on the 3-5 strongest bullish points.
- Complete your ENTIRE argument in a SINGLE response.

Respond only with your bullish financial analysis. No disclaimers or meta-commentary."""

        user_prompt = f"""Analyze this stock from a bullish perspective:

MARKET DATA:
{market_research_report}

SENTIMENT:
{sentiment_report}

NEWS:
{news_report}

FUNDAMENTALS:
{fundamentals_report}

DEBATE HISTORY:
{history}

BEAR'S LAST ARGUMENT:
{current_response}

PAST LEARNINGS:
{past_memory_str if past_memory_str else "None"}

Provide your bullish case for this investment."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        step_timer.start_step("bull_researcher")
        add_log("agent", "bull_researcher", f"🐂 Bull Analyst calling LLM...")
        t0 = time.time()
        response = llm.invoke(messages)
        elapsed = time.time() - t0
        add_log("llm", "bull_researcher", f"LLM responded in {elapsed:.1f}s ({len(response.content)} chars)")
        add_log("agent", "bull_researcher", f"✅ Bull argument ready: {response.content[:300]}...")
        step_timer.end_step("bull_researcher", "completed", response.content[:200])
        symbol_progress.step_done(state["company_of_interest"], "bull_researcher")
        step_timer.set_details("bull_researcher", {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt[:3000],
            "response": response.content[:3000],
            "tool_calls": [],
        })

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
