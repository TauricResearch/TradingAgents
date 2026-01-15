from langchain_core.messages import AIMessage
import time
import json
from tradingagents.agents.utils.schemas import ConfidenceOutput


def create_bear_researcher(llm, memory):
    # Bind structured output
    structured_llm = llm.with_structured_output(ConfidenceOutput)

    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""ROLE: Hostile Bearish Litigator.
OBJECTIVE: Win the debate by destroying the Bull case.
STYLE: Aggressive, data-driven, direct. NO "I agree with my colleague." NO politeness.

INSTRUCTIONS:
1. Expose Risks: Highlight failure points, debt loads, and macro headwinds.
2. Attack Bull Points: If Bull cites "growth," cite "saturation" and "valuation bubble."
3. Evidence First: Every claim must cite specific data points.

WARNING: You will be Fact-Checked. If you lie about numbers, the Trade will be REJECTED.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a direct, adversarial style, refuting the bull analyst's points with data.

Resources available:

Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the stock. You must also address reflections and learn from lessons and mistakes you made in the past.
        WARNING: You must provide a clear rationale and a numeric confidence score (0.0 to 1.0).
        """
 
        # Call structured LLM
        result = structured_llm.invoke(prompt)
        
        argument = f"Bear Analyst: {result.rationale}"
        confidence = result.confidence

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
            "confidence": confidence # Local confidence
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "bear_confidence": confidence # Global floor for Gatekeeper
        }

    return bear_node
