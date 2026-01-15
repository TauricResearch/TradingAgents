from langchain_core.messages import AIMessage
import time
import json
from tradingagents.agents.utils.schemas import ConfidenceOutput


def create_bull_researcher(llm, memory):
    # Bind structured output
    structured_llm = llm.with_structured_output(ConfidenceOutput)

    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

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

        prompt = f"""ROLE: Hostile Bullish Litigator.
OBJECTIVE: Win the debate by destroying the Bear case.
STYLE: Aggressive, data-driven, direct. NO "I agree with my colleague." NO politeness.

INSTRUCTIONS:
1. Growth Potential: Maximize revenue projections.
2. Attack Bear Points: If the Bear cites "risk," cite "mitigation" and "opportunity cost."
3. Evidence First: Every claim must cite specific data points (e.g., "Revenue +5%").

WARNING: You will be Fact-Checked. If you lie about numbers (e.g., "500% growth"), the Trade will be REJECTED.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a direct, adversarial style, refuting the bear analyst's points with data.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position. You must also address reflections and learn from lessons and mistakes you made in the past.
        WARNING: You must provide a clear rationale and a numeric confidence score (0.0 to 1.0).
        """
 
        # Call structured LLM
        result = structured_llm.invoke(prompt)
        
        argument = f"Bull Analyst: {result.rationale}"
        confidence = result.confidence

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
            "confidence": confidence # Local confidence for the debate state
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "bull_confidence": confidence # Global floor for Gatekeeper
        }

    return bull_node
