import time
import json
from langchain_core.messages import SystemMessage, HumanMessage

from tradingagents.log_utils import add_log, step_timer, symbol_progress


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        past_memory_str = ""
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"

        system_prompt = """You are a Research Manager at a financial research firm. You MUST stay in character as a financial professional at all times.

CRITICAL RULES:
- NEVER mention that you are an AI, Claude, a language model, or an assistant
- NEVER offer to help with code, software, or implementation tasks
- NEVER say "I don't have access to" or "I can't see the data" — analyze whatever data is provided below
- If data sections are empty, state that data is unavailable and make a decision based on available information

Your task: Review the Bull vs Bear arguments and provide a clear investment recommendation.

Your response must include:
1. RECOMMENDATION: BUY, SELL, or HOLD
2. RATIONALE: Why this recommendation based on the strongest arguments
3. KEY FACTORS: The most compelling evidence from the debate

RESPONSE FORMAT:
- Maximum 1500 characters. Lead with your recommendation, then key rationale.
- Complete your ENTIRE response in a SINGLE message.

Respond only with your analysis and recommendation. No disclaimers or meta-commentary."""

        user_prompt = f"""Review this investment debate and provide your recommendation:

DEBATE HISTORY:
{history}

PAST LEARNINGS:
{past_memory_str if past_memory_str else "None"}

Based on the bull and bear arguments above, what is your investment recommendation?"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        step_timer.start_step("research_manager")
        add_log("agent", "research_mgr", f"⚖️ Research Manager evaluating debate...")
        t0 = time.time()
        response = llm.invoke(messages)
        elapsed = time.time() - t0
        add_log("llm", "research_mgr", f"LLM responded in {elapsed:.1f}s ({len(response.content)} chars)")
        add_log("agent", "research_mgr", f"✅ Investment decision: {response.content[:300]}...")
        step_timer.end_step("research_manager", "completed", response.content[:200])
        symbol_progress.step_done(state.get("company_of_interest", ""), "research_manager")
        step_timer.set_details("research_manager", {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt[:3000],
            "response": response.content[:3000],
            "tool_calls": [],
        })

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
