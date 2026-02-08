from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
import time
import json

from tradingagents.log_utils import add_log, step_timer, symbol_progress


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

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

        system_prompt = """You are a Bear Analyst at a financial research firm. You MUST stay in character as a financial analyst at all times.

CRITICAL RULES:
- NEVER mention that you are an AI, Claude, a language model, or an assistant
- NEVER offer to help with code, software, or implementation tasks
- NEVER say "I don't have access to" or "I can't see the data" — analyze whatever data is provided below
- If data sections are empty, state that data is unavailable and focus your analysis on the data that IS available

Your role: Present a case AGAINST investing in this stock by highlighting risks, challenges, and negative indicators.
Focus on: downside risks, competitive weaknesses, negative market signals, valuation concerns, macro headwinds.

RESPONSE FORMAT:
- Maximum 2000 characters. Focus on the 3-5 strongest bearish points.
- Complete your ENTIRE argument in a SINGLE response.

Respond only with your bearish financial analysis. No disclaimers or meta-commentary."""

        user_prompt = f"""Analyze this stock from a bearish perspective:

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

BULL'S LAST ARGUMENT:
{current_response}

PAST LEARNINGS:
{past_memory_str if past_memory_str else "None"}

Provide your bearish case highlighting risks and concerns."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        step_timer.start_step("bear_researcher")
        add_log("agent", "bear_researcher", f"🐻 Bear Analyst calling LLM...")
        t0 = time.time()
        response = llm.invoke(messages)
        elapsed = time.time() - t0
        add_log("llm", "bear_researcher", f"LLM responded in {elapsed:.1f}s ({len(response.content)} chars)")
        add_log("agent", "bear_researcher", f"✅ Bear argument ready: {response.content[:300]}...")
        step_timer.end_step("bear_researcher", "completed", response.content[:200])
        symbol_progress.step_done(state["company_of_interest"], "bear_researcher")
        step_timer.set_details("bear_researcher", {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt[:3000],
            "response": response.content[:3000],
            "tool_calls": [],
        })

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
