import time
import json
from langchain_core.messages import SystemMessage, HumanMessage

from tradingagents.log_utils import add_log, step_timer, symbol_progress


def create_risky_debator(llm):
    def risky_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        risky_history = risk_debate_state.get("risky_history", "")

        current_safe_response = risk_debate_state.get("current_safe_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        system_prompt = """You are an Aggressive Risk Analyst at a financial advisory firm. You MUST stay in character as a financial analyst at all times.

CRITICAL RULES:
- NEVER mention that you are an AI, Claude, a language model, or an assistant
- NEVER offer to help with code, software, or implementation tasks
- NEVER say "I don't have access to" or "I can't see the data" — analyze whatever data is provided below
- If data sections are empty, state that data is unavailable and focus your analysis on the data that IS available

Your role: Advocate for growth-oriented, higher-risk investment strategies that maximize potential returns.
Focus on: growth opportunities, upside potential, momentum signals, and why bolder strategies are justified.
Counter conservative arguments with data-driven rebuttals.

RESPONSE FORMAT:
- Maximum 2000 characters. Focus on the 3-5 strongest growth-oriented points.
- Complete your ENTIRE argument in a SINGLE response.

Respond only with your aggressive financial analysis. No disclaimers or meta-commentary."""

        user_prompt = f"""Provide the aggressive/growth-oriented perspective on this investment:

TRADER'S DECISION:
{trader_decision}

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

CONSERVATIVE ANALYST'S ARGUMENT:
{current_safe_response if current_safe_response else "None yet"}

NEUTRAL ANALYST'S ARGUMENT:
{current_neutral_response if current_neutral_response else "None yet"}

Present your aggressive/growth-oriented case."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        step_timer.start_step("aggressive_analyst")
        add_log("agent", "aggressive", f"🔥 Aggressive Analyst calling LLM...")
        t0 = time.time()
        response = llm.invoke(messages)
        elapsed = time.time() - t0
        add_log("llm", "aggressive", f"LLM responded in {elapsed:.1f}s ({len(response.content)} chars)")
        add_log("agent", "aggressive", f"✅ Aggressive argument ready: {response.content[:300]}...")
        step_timer.end_step("aggressive_analyst", "completed", response.content[:200])
        symbol_progress.step_done(state["company_of_interest"], "aggressive_analyst")
        step_timer.set_details("aggressive_analyst", {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt[:3000],
            "response": response.content[:3000],
            "tool_calls": [],
        })

        argument = f"Risky Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risky_history + "\n" + argument,
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Risky",
            "current_risky_response": argument,
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return risky_node
