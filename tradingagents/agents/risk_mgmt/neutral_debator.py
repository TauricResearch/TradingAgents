import time
import json
from tradingagents.agents.utils.agent_utils import (
    build_debate_brief,
    extract_feedback_snapshot,
    get_language_instruction,
    get_snapshot_template,
    get_snapshot_writing_instruction,
    localize_role_name,
    strip_feedback_snapshot,
    truncate_for_prompt,
)


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        neutral_history = risk_debate_state.get("neutral_history", "")
        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        aggressive_snapshot = risk_debate_state.get("aggressive_snapshot", "")
        conservative_snapshot = risk_debate_state.get("conservative_snapshot", "")
        neutral_snapshot = risk_debate_state.get("neutral_snapshot", "")
        debate_brief = risk_debate_state.get("debate_brief", "")

        market_research_report = truncate_for_prompt(state["market_report"])
        sentiment_report = truncate_for_prompt(state["sentiment_report"])
        news_report = truncate_for_prompt(state["news_report"])
        fundamentals_report = truncate_for_prompt(state["fundamentals_report"])

        trader_decision = truncate_for_prompt(state["trader_investment_plan"])

        prompt = f"""As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. You prioritize a well-rounded approach, evaluating the upsides and downsides while factoring in broader market trends, potential economic shifts, and diversification strategies.Here is the trader's decision:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. Use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Rolling risk debate brief: {debate_brief}
Your latest feedback snapshot: {neutral_snapshot}
Latest aggressive feedback snapshot: {aggressive_snapshot}
Latest conservative feedback snapshot: {conservative_snapshot}
Last aggressive argument body: {current_aggressive_response}
Last conservative argument body: {current_conservative_response}
If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Challenge each of their points to illustrate why a moderate risk strategy might offer the best of both worlds, providing growth potential while safeguarding against extreme volatility. Focus on debating rather than simply presenting data, aiming to show that a balanced view can lead to the most reliable outcomes. Output conversationally as if you are speaking without any special formatting.
After your normal argument, append an exact block using this template:
{get_snapshot_template()}
{get_snapshot_writing_instruction()}{get_language_instruction()}"""

        response = llm.invoke(prompt)
        raw_content = response.content
        argument_body = strip_feedback_snapshot(raw_content)
        argument = f"{localize_role_name('Neutral Analyst')}: {argument_body}"
        new_neutral_snapshot = extract_feedback_snapshot(raw_content)
        new_debate_brief = build_debate_brief(
            {
                "Aggressive Analyst": aggressive_snapshot,
                "Conservative Analyst": conservative_snapshot,
                "Neutral Analyst": new_neutral_snapshot,
            },
            latest_speaker="Neutral Analyst",
        )

        new_risk_debate_state = {
            "history": risk_debate_state.get("history", "") + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "aggressive_snapshot": aggressive_snapshot,
            "conservative_snapshot": conservative_snapshot,
            "neutral_snapshot": new_neutral_snapshot,
            "debate_brief": new_debate_brief,
            "judge_decision": risk_debate_state.get("judge_decision", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
