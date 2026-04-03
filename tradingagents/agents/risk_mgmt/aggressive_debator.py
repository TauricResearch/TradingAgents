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


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        aggressive_history = risk_debate_state.get("aggressive_history", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")
        aggressive_snapshot = risk_debate_state.get("aggressive_snapshot", "")
        conservative_snapshot = risk_debate_state.get("conservative_snapshot", "")
        neutral_snapshot = risk_debate_state.get("neutral_snapshot", "")
        debate_brief = risk_debate_state.get("debate_brief", "")

        market_research_report = truncate_for_prompt(state["market_report"])
        sentiment_report = truncate_for_prompt(state["sentiment_report"])
        news_report = truncate_for_prompt(state["news_report"])
        fundamentals_report = truncate_for_prompt(state["fundamentals_report"])

        trader_decision = truncate_for_prompt(state["trader_investment_plan"])

        prompt = f"""As the Aggressive Risk Analyst, your role is to actively champion high-reward, high-risk opportunities, emphasizing bold strategies and competitive advantages. When evaluating the trader's decision or plan, focus intently on the potential upside, growth potential, and innovative benefits—even when these come with elevated risk. Use the provided market data and sentiment analysis to strengthen your arguments and challenge the opposing views. Specifically, respond directly to each point made by the conservative and neutral analysts, countering with data-driven rebuttals and persuasive reasoning. Highlight where their caution might miss critical opportunities or where their assumptions may be overly conservative. Here is the trader's decision:

{trader_decision}

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. Incorporate insights from the following sources into your arguments:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Rolling risk debate brief: {debate_brief}
Your latest feedback snapshot: {aggressive_snapshot}
Latest conservative feedback snapshot: {conservative_snapshot}
Latest neutral feedback snapshot: {neutral_snapshot}
Last conservative argument body: {current_conservative_response}
Last neutral argument body: {current_neutral_response}
If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a high-risk approach is optimal. Output conversationally as if you are speaking without any special formatting.
After your normal argument, append an exact block using this template:
{get_snapshot_template()}
{get_snapshot_writing_instruction()}{get_language_instruction()}"""

        response = llm.invoke(prompt)
        raw_content = response.content
        argument_body = strip_feedback_snapshot(raw_content)
        argument = f"{localize_role_name('Aggressive Analyst')}: {argument_body}"
        new_aggressive_snapshot = extract_feedback_snapshot(raw_content)
        new_debate_brief = build_debate_brief(
            {
                "Aggressive Analyst": new_aggressive_snapshot,
                "Conservative Analyst": conservative_snapshot,
                "Neutral Analyst": neutral_snapshot,
            },
            latest_speaker="Aggressive Analyst",
        )

        new_risk_debate_state = {
            "history": risk_debate_state.get("history", "") + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "aggressive_snapshot": new_aggressive_snapshot,
            "conservative_snapshot": conservative_snapshot,
            "neutral_snapshot": neutral_snapshot,
            "debate_brief": new_debate_brief,
            "judge_decision": risk_debate_state.get("judge_decision", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
