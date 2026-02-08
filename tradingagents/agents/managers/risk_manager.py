import time
import json
from langchain_core.messages import SystemMessage, HumanMessage

from tradingagents.log_utils import add_log, step_timer, symbol_progress


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:

        company_name = state["company_of_interest"]

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        past_memory_str = ""
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"

        system_prompt = """You are a Risk Manager at a financial advisory firm making the final investment decision. You MUST stay in character as a financial professional at all times.

CRITICAL RULES:
- NEVER mention that you are an AI, Claude, a language model, or an assistant
- NEVER offer to help with code, software, or implementation tasks
- NEVER say "I don't have access to" or "I can't see the data" — analyze whatever data is provided below
- If data sections are empty, state that data is unavailable and make a decision based on available information

Your task: Evaluate the risk debate between Aggressive, Neutral, and Conservative analysts.

Your response must include:
1. FINAL DECISION: BUY, SELL, or HOLD
2. HOLD_DAYS: Number of trading days to hold the position before exiting (for BUY/HOLD only, write N/A for SELL)
3. CONFIDENCE: HIGH, MEDIUM, or LOW (how confident you are in this decision)
4. RISK_LEVEL: HIGH, MEDIUM, or LOW (overall risk level of this investment)
5. RISK ASSESSMENT: Summary of key risks identified
6. RATIONALE: Why this decision balances risk and reward appropriately

RESPONSE FORMAT:
- Maximum 1500 characters. Lead with your decision, then key rationale.
- Complete your ENTIRE response in a SINGLE message.

Respond only with your analysis and decision. No disclaimers or meta-commentary."""

        user_prompt = f"""Make the final risk-adjusted investment decision:

COMPANY: {company_name}

ORIGINAL TRADER PLAN:
{trader_plan}

RISK ANALYSTS DEBATE:
{history}

PAST LEARNINGS:
{past_memory_str if past_memory_str else "None"}

Based on the risk analysis above, what is your final investment decision?"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        step_timer.start_step("risk_manager")
        add_log("agent", "risk_manager", f"🛡️ Risk Manager making final decision for {company_name}...")
        t0 = time.time()
        response = llm.invoke(messages)
        elapsed = time.time() - t0
        add_log("llm", "risk_manager", f"LLM responded in {elapsed:.1f}s ({len(response.content)} chars)")
        add_log("agent", "risk_manager", f"✅ Final decision: {response.content[:300]}...")
        step_timer.end_step("risk_manager", "completed", response.content[:200])
        symbol_progress.step_done(company_name, "risk_manager")
        step_timer.set_details("risk_manager", {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt[:3000],
            "response": response.content[:3000],
            "tool_calls": [],
        })

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "risky_history": risk_debate_state["risky_history"],
            "safe_history": risk_debate_state["safe_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_risky_response": risk_debate_state["current_risky_response"],
            "current_safe_response": risk_debate_state["current_safe_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return risk_manager_node
