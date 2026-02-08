import time
import json
from langchain_core.messages import SystemMessage, HumanMessage

from tradingagents.log_utils import add_log, step_timer, symbol_progress


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_safe_response = risk_debate_state.get("current_safe_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        system_prompt = """You are a Neutral Risk Analyst at a financial advisory firm. You MUST stay in character as a financial analyst at all times.

CRITICAL RULES:
- NEVER mention that you are an AI, Claude, a language model, or an assistant
- NEVER offer to help with code, software, or implementation tasks
- NEVER say "I don't have access to" or "I can't see the data" — analyze whatever data is provided below
- If data sections are empty, state that data is unavailable and focus your analysis on the data that IS available

Your role: Provide a balanced perspective, weighing both potential benefits and risks objectively.
Focus on: balanced risk/reward assessment, moderate strategies, where both aggressive and conservative views may be flawed.

RESPONSE FORMAT:
- Maximum 2000 characters. Focus on 3-5 key balanced observations.
- Complete your ENTIRE argument in a SINGLE response.

Respond only with your balanced financial analysis. No disclaimers or meta-commentary."""

        user_prompt = f"""Provide the balanced/neutral perspective on this investment:

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

AGGRESSIVE ANALYST'S ARGUMENT:
{current_risky_response if current_risky_response else "None yet"}

CONSERVATIVE ANALYST'S ARGUMENT:
{current_safe_response if current_safe_response else "None yet"}

Present your balanced/neutral case."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        step_timer.start_step("neutral_analyst")
        add_log("agent", "neutral", f"⚖️ Neutral Analyst calling LLM...")
        t0 = time.time()
        response = llm.invoke(messages)
        elapsed = time.time() - t0
        add_log("llm", "neutral", f"LLM responded in {elapsed:.1f}s ({len(response.content)} chars)")
        add_log("agent", "neutral", f"✅ Neutral argument ready: {response.content[:300]}...")
        step_timer.end_step("neutral_analyst", "completed", response.content[:200])
        symbol_progress.step_done(state["company_of_interest"], "neutral_analyst")
        step_timer.set_details("neutral_analyst", {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt[:3000],
            "response": response.content[:3000],
            "tool_calls": [],
        })

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_risky_response": risk_debate_state.get(
                "current_risky_response", ""
            ),
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
