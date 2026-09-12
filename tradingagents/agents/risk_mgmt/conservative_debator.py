from collections.abc import Mapping
from typing import Any

from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
)
from tradingagents.dataflows import config


def build_conservative_prompt(state: Mapping[str, Any], *, output_language: str) -> str:
    """Build the Conservative Risk Analyst prompt without invoking the model."""
    risk_debate_state = state["risk_debate_state"]
    history = risk_debate_state.get("history", "")

    current_aggressive_response = opponent_argument_or_opening(
        risk_debate_state.get("current_aggressive_response", ""), "aggressive analyst"
    )
    current_neutral_response = opponent_argument_or_opening(
        risk_debate_state.get("current_neutral_response", ""), "neutral analyst"
    )

    market_research_report = state["market_report"]
    sentiment_report = state["sentiment_report"]
    news_report = state["news_report"]
    fundamentals_report = state["fundamentals_report"]
    instrument_context = get_instrument_context_from_state(state)

    trader_decision = state["trader_investment_plan"]

    return f"""As the Conservative Risk Analyst, your primary objective is to protect assets, minimize volatility, and ensure steady, reliable growth. You prioritize stability, security, and risk mitigation, carefully assessing potential losses, economic downturns, and market volatility. When evaluating the trader's decision or plan, critically examine high-risk elements, pointing out where the decision may expose the firm to undue risk and where more cautious alternatives could secure long-term gains. Here is the trader's decision:

{trader_decision}

Your task is to actively counter the arguments of the Aggressive and Neutral Analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability. Respond directly to their points, drawing from the following data sources to build a convincing case for a low-risk approach adjustment to the trader's decision:

{instrument_context}
Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage by questioning their optimism and emphasizing the potential downsides they may have overlooked. Address each of their counterpoints to showcase why a conservative stance is ultimately the safest path for the firm's assets. Focus on debating and critiquing their arguments to demonstrate the strength of a low-risk strategy over their approaches. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction(output_language)


def apply_conservative_output(state: Mapping[str, Any], output: str) -> dict[str, Any]:
    risk_debate_state = state["risk_debate_state"]
    argument = f"Conservative Analyst: {output}"
    return {
        "risk_debate_state": {
            "history": risk_debate_state.get("history", "") + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", "") + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state["count"] + 1,
        }
    }


def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        language = config.get_config().get("output_language", "English")
        response = llm.invoke(build_conservative_prompt(state, output_language=language))
        return apply_conservative_output(state, response.content)

    return conservative_node
