from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )

        if current_response.strip():
            engagement_instruction = (
                "- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, "
                "addressing concerns thoroughly and showing why the bull perspective holds stronger merit.\n"
                "- Engagement: Present your argument in a conversational style, engaging directly with the bear "
                "analyst's points and debating effectively rather than just listing data.\n\n"
                f"Last bear argument: {current_response}\n"
                "Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage "
                "in a dynamic debate that demonstrates the strengths of the bull position."
            )
        else:
            # The debate opens with this speaker: no bear argument exists yet,
            # so prompting a rebuttal makes the model fabricate one (#1176).
            engagement_instruction = (
                "- This is the opening statement of the debate: the bear analyst has not spoken yet. Do not claim, "
                "paraphrase, or rebut any bear argument, because none exists yet.\n"
                "- Present your bull case on its own merits, using the provided research and data as evidence.\n\n"
                "Open with a clear statement of your position, then support it with the strongest available evidence."
            )

        prompt = f"""You are a Bull Analyst advocating for investing in the {target_label}. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
{engagement_instruction}

Resources available:
{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
Conversation history of the debate: {history}
""" + get_language_instruction()

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
