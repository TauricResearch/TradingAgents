from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.agents.utils.agent_utils import (
    build_cacheable_system_content,
    get_instrument_context_from_state,
    get_language_instruction,
)


def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        instrument_context = get_instrument_context_from_state(state)

        trader_decision = state["trader_investment_plan"]
        system_content = build_cacheable_system_content(
            "You are the Conservative Risk Analyst. Your primary objective is to protect assets, minimize volatility, and ensure steady, reliable growth. You prioritize stability, security, and risk mitigation, carefully assessing potential losses, economic downturns, and market volatility."
            " When evaluating the trader's decision or plan, critically examine high-risk elements, pointing out where the decision may expose the firm to undue risk and where more cautious alternatives could secure long-term gains."
            " Actively counter the arguments of the Aggressive and Neutral Analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability."
            " If there are no responses from the other viewpoints yet, present your own argument based on the available data."
            " Focus on debating and critiquing their arguments to demonstrate the strength of a low-risk strategy over their approaches, not just presenting data."
            " Output conversationally as if you are speaking without any special formatting."
            + get_language_instruction(),
            llm,
        )
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(
                content=f"""Analysis context:
- Trader decision: {trader_decision}
- Instrument context: {instrument_context}
- Market research report: {market_research_report}
- Social media sentiment report: {sentiment_report}
- Latest world affairs report: {news_report}
- Company fundamentals report: {fundamentals_report}
- Current conversation history: {history}
- Last aggressive argument: {current_aggressive_response}
- Last neutral argument: {current_neutral_response}

Engage by questioning their optimism and emphasizing the potential downsides they may have overlooked. Address each of their counterpoints to showcase why a conservative stance is ultimately the safest path for the firm's assets.""",
            ),
        ]

        response = llm.invoke(messages)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
