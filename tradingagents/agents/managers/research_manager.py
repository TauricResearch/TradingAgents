from tradingagents.agents.utils.agent_utils import build_instrument_context, get_memory_matches
from tradingagents.schemas import build_decision_output_instructions, ensure_structured_decision_json


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(
            state["company_of_interest"],
            state.get("instrument_profile"),
        )
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = get_memory_matches(memory, curr_situation)

        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""As the research manager and evidence arbiter, critically evaluate the bull and bear debate and produce a structured investment view for the trader.

{instrument_context}

Your job:
- weigh the strongest bullish and bearish evidence
- reduce action bias; use NO_TRADE when the evidence is too weak or conflicted
- focus on evidence arbitration rather than rhetorical style
- make the catalysts and invalidators explicit

Use these objective reports for grounding:
Market Report:
{market_research_report}

Sentiment Report:
{sentiment_report}

News Report:
{news_report}

Fundamentals Report:
{fundamentals_report}

Debate History:
{history}

Lessons from past mistakes:
{past_memory_str or "No past reflections available."}

{build_decision_output_instructions("research manager investment plan")}"""
        response = llm.invoke(prompt)
        decision_json = ensure_structured_decision_json(response.content)

        new_investment_debate_state = {
            "judge_decision": decision_json,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": decision_json,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": decision_json,
        }

    return research_manager_node
