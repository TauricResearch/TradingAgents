from langchain_core.prompts import ChatPromptTemplate

from tradingagents.agents.utils.agent_utils import get_language_instruction


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are the Aggressive Risk Analyst. Your role is to actively champion high-reward, high-risk opportunities, emphasizing bold strategies and competitive advantages. When evaluating the trader's decision or plan, focus intently on the potential upside, growth potential, and innovative benefits-even when these come with elevated risk."
                " Use the provided market data and sentiment analysis to strengthen your arguments and challenge the opposing views."
                " Specifically, respond directly to each point made by the conservative and neutral analysts, countering with data-driven rebuttals and persuasive reasoning."
                " Highlight where their caution might miss critical opportunities or where their assumptions may be overly conservative."
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
- Last conservative argument: {current_conservative_response}
- Last neutral argument: {current_neutral_response}

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms.""",
            ),
        ])

        response = (prompt | llm).invoke({})

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
