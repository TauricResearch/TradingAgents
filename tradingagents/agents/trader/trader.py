import functools

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    build_optional_decision_context,
    summarize_structured_signal,
)
from tradingagents.agents.utils.decision_utils import build_structured_decision


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        portfolio_context = state.get("portfolio_context", "")
        peer_context = state.get("peer_context", "")
        research_plan_structured = state.get("investment_plan_structured") or {}

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        decision_context = build_optional_decision_context(
            portfolio_context,
            peer_context,
            peer_context_mode=state.get("peer_context_mode", "UNSPECIFIED"),
            max_chars=500,
        )
        context = {
            "role": "user",
            "content": (
                f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. "
                f"{instrument_context} This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. "
                "Use this plan as a foundation for evaluating your next trading decision.\n\n"
                f"Research signal summary: {summarize_structured_signal(research_plan_structured)}\n"
                f"{decision_context}\n\n"
                f"Proposed Investment Plan: {investment_plan}\n\n"
                "Leverage these insights to make an informed and strategic decision."
            ),
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a trading agent analyzing market data to make investment decisions. "
                    "Based on your analysis, provide a specific recommendation to buy, sell, or hold. "
                    "Include a machine-readable line formatted exactly as `TRADER_RATING: BUY|HOLD|SELL` and "
                    "always conclude your response with `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`. "
                    "Do not emit tool calls or ask for more data. "
                    f"Apply lessons from past decisions to strengthen your analysis. Here are reflections from similar situations you traded in and the lessons learned: {past_memory_str}"
                ),
            },
            context,
        ]

        result = llm.invoke(messages)
        structured_plan = build_structured_decision(
            result.content,
            default_rating="HOLD",
            peer_context_mode=state.get("peer_context_mode", "UNSPECIFIED"),
            context_usage={
                "portfolio_context": bool(str(portfolio_context).strip()),
                "peer_context": bool(str(peer_context).strip()),
            },
        )

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "trader_investment_plan_structured": structured_plan,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
