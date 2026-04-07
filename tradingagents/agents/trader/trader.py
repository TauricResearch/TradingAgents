import functools

from tradingagents.agents.utils.agent_utils import build_instrument_context, get_memory_matches
from tradingagents.schemas import build_decision_output_instructions, ensure_structured_decision_json


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name, state.get("instrument_profile"))
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = get_memory_matches(memory, curr_situation)

        past_memory_str = ""
        if past_memories:
            for rec in past_memories:
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        context = {
            "role": "user",
            "content": (
                f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. "
                f"{instrument_context} This plan incorporates insights from market trends, macro context, sentiment, news, and fundamentals. "
                f"Use this plan as a foundation for your execution decision.\n\nProposed Investment Plan JSON: {investment_plan}\n\n"
                "Leverage these insights to make an informed and strategic decision."
            ),
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a trading agent analyzing market data to make execution-ready investment decisions. "
                    "Translate the research manager's view into a concrete trade recommendation with entry logic, exit logic, position sizing, risk limits, catalysts, and invalidators. "
                    "Use NO_TRADE when the setup is not actionable or lacks a favorable risk/reward. "
                    f"Apply lessons from similar situations: {past_memory_str} "
                    f"{build_decision_output_instructions('trader execution plan')}"
                ),
            },
            context,
        ]

        result = llm.invoke(messages)
        decision_json = ensure_structured_decision_json(result.content)

        return {
            "messages": [result],
            "trader_investment_plan": decision_json,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
