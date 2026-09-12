from collections.abc import Mapping
from typing import Any

from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
)
from tradingagents.dataflows import config


def build_bear_prompt(state: Mapping[str, Any], *, output_language: str) -> str:
    """Build the Bear Analyst prompt without invoking the model."""
    investment_debate_state = state["investment_debate_state"]
    history = investment_debate_state.get("history", "")
    current_response = opponent_argument_or_opening(
        investment_debate_state.get("current_response", ""), "bull analyst"
    )
    asset_type = state.get("asset_type", "stock")
    target_label = "stock" if asset_type == "stock" else "asset"
    fundamentals_label = (
        "Company fundamentals report"
        if asset_type == "stock"
        else "Asset fundamentals report (may be unavailable for crypto)"
    )
    return f"""You are a Bear Analyst making the case against investing in the {target_label}. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

{get_instrument_context_from_state(state)}
Market research report: {state["market_report"]}
Social media sentiment report: {state["sentiment_report"]}
Latest world affairs news: {state["news_report"]}
{fundamentals_label}: {state["fundamentals_report"]}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the {target_label}.
""" + get_language_instruction(output_language)


def apply_bear_output(state: Mapping[str, Any], output: str) -> dict[str, Any]:
    investment_debate_state = state["investment_debate_state"]
    history = investment_debate_state.get("history", "")
    bear_history = investment_debate_state.get("bear_history", "")
    argument = f"Bear Analyst: {output}"
    return {
        "investment_debate_state": {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }
    }


def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        language = config.get_config().get("output_language", "English")
        response = llm.invoke(build_bear_prompt(state, output_language=language))
        return apply_bear_output(state, response.content)

    return bear_node
