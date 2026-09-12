from collections.abc import Mapping
from typing import Any

from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
)
from tradingagents.dataflows import config


def build_neutral_prompt(state: Mapping[str, Any], *, output_language: str) -> str:
    """Build the Neutral Risk Analyst prompt without invoking the model."""
    risk_debate_state = state["risk_debate_state"]
    history = risk_debate_state.get("history", "")

    current_aggressive_response = opponent_argument_or_opening(
        risk_debate_state.get("current_aggressive_response", ""), "aggressive analyst"
    )
    current_conservative_response = opponent_argument_or_opening(
        risk_debate_state.get("current_conservative_response", ""), "conservative analyst"
    )

    market_research_report = state["market_report"]
    sentiment_report = state["sentiment_report"]
    news_report = state["news_report"]
    fundamentals_report = state["fundamentals_report"]
    instrument_context = get_instrument_context_from_state(state)

    trader_decision = state["trader_investment_plan"]

    return f"""As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. You prioritize a well-rounded approach, evaluating the upsides and downsides while factoring in broader market trends, potential economic shifts, and diversification strategies.Here is the trader's decision:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. Use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

{instrument_context}
Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the conservative analyst: {current_conservative_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Challenge each of their points to illustrate why a moderate risk strategy might offer the best of both worlds, providing growth potential while safeguarding against extreme volatility. Focus on debating rather than simply presenting data, aiming to show that a balanced view can lead to the most reliable outcomes. Output conversationally as if you are speaking without any special formatting.""" + get_language_instruction(output_language)


def apply_neutral_output(state: Mapping[str, Any], output: str) -> dict[str, Any]:
    risk_debate_state = state["risk_debate_state"]
    argument = f"Neutral Analyst: {output}"
    return {
        "risk_debate_state": {
            "history": risk_debate_state.get("history", "") + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", "") + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }
    }


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        language = config.get_config().get("output_language", "English")
        response = llm.invoke(build_neutral_prompt(state, output_language=language))
        return apply_neutral_output(state, response.content)

    return neutral_node
