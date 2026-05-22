from langchain_core.prompts import ChatPromptTemplate

from tradingagents.agents.utils.agent_utils import get_language_instruction


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are the Neutral Risk Analyst. Your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. You prioritize a well-rounded approach, evaluating the upsides and downsides while factoring in broader market trends, potential economic shifts, and diversification strategies."
                " Challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious."
                + get_language_instruction(),
            ),
            (
                "human",
                f"""Analysis context:
- Trader decision: {trader_decision}
- Market research report: {market_research_report}
- Social media sentiment report: {sentiment_report}
- Latest world affairs report: {news_report}
- Company fundamentals report: {fundamentals_report}
- Current conversation history: {history}
- Last aggressive argument: {current_aggressive_response}
- Last conservative argument: {current_conservative_response}

Use insights from the data sources to support a moderate, sustainable strategy to adjust the trader's decision. Engage actively by analyzing both sides critically and advocate for a more balanced approach.""",
            ),
        ])

        response = (prompt | llm).invoke({})

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
