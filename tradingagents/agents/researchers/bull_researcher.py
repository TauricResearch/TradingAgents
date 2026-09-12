from collections.abc import Mapping
from typing import Any

from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
)
from tradingagents.dataflows import config


def build_bull_prompt(state: Mapping[str, Any], *, output_language: str) -> str:
    """Build the Bull Analyst prompt without invoking the model."""
    investment_debate_state = state["investment_debate_state"]
    history = investment_debate_state.get("history", "")
    current_response = opponent_argument_or_opening(
        investment_debate_state.get("current_response", ""), "bear analyst"
    )
    asset_type = state.get("asset_type", "stock")
    target_label = "stock" if asset_type == "stock" else "asset"
    fundamentals_label = (
        "Company fundamentals report"
        if asset_type == "stock"
        else "Asset fundamentals report (may be unavailable for crypto)"
    )
    return f"""You are a Bull Analyst advocating for investing in the {target_label}. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
{get_instrument_context_from_state(state)}
Market research report: {state["market_report"]}
Social media sentiment report: {state["sentiment_report"]}
Latest world affairs news: {state["news_report"]}
{fundamentals_label}: {state["fundamentals_report"]}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
""" + get_language_instruction(output_language)


def apply_bull_output(state: Mapping[str, Any], output: str) -> dict[str, Any]:
    investment_debate_state = state["investment_debate_state"]
    history = investment_debate_state.get("history", "")
    bull_history = investment_debate_state.get("bull_history", "")
    argument = f"Bull Analyst: {output}"
    return {
        "investment_debate_state": {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }
    }


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        language = config.get_config().get("output_language", "English")
        response = llm.invoke(build_bull_prompt(state, output_language=language))
        return apply_bull_output(state, response.content)

    return bull_node
