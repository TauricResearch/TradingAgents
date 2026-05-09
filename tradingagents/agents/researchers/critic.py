"""Critic: a single balanced analyst that replaces the Bull/Bear debate.

Variation 2 of the experiment. Instead of two adversarial researchers
talking past each other for N rounds, one analyst is asked to argue
both sides honestly and arrive at a recommendation. Eliminates the
performative back-and-forth while preserving devil's-advocate framing.
"""

from __future__ import annotations


def create_critic(llm):
    def critic_node(state) -> dict:
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        prompt = f"""You are an Investment Critic. Your job is to argue both sides of the case honestly — not to advocate, not to be balanced for its own sake, but to surface the strongest version of each argument and decide which side actually wins on the evidence.

Structure your response in three labelled sections:

**Bull Case**: The strongest argument for owning this stock right now. Specific catalysts, growth drivers, valuation support.

**Bear Case**: The strongest argument against. Specific risks, headwinds, valuation concerns, sentiment cracks.

**Verdict**: Which side wins on the evidence available, and why. Be decisive; reserve a balanced verdict only when the evidence is genuinely symmetric.

Resources:
- Market research report: {market_research_report}
- Social media sentiment: {sentiment_report}
- News and macro: {news_report}
- Company fundamentals: {fundamentals_report}

Steelman both sides. The Verdict must commit."""

        response = llm.invoke(prompt)
        argument = f"Investment Critic:\n{response.content}"

        investment_debate_state = state["investment_debate_state"]
        new_state = {
            "history": argument,
            "bull_history": argument,
            "bear_history": argument,
            "current_response": argument,
            "judge_decision": investment_debate_state.get("judge_decision", ""),
            "count": investment_debate_state.get("count", 0) + 1,
        }
        return {"investment_debate_state": new_state}

    return critic_node
