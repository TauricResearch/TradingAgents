

def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        instrument_type = state.get("instrument_type", "stock")

        if instrument_type == "polymarket":
            market_question = state.get("market_question", "")
            yes_price = state.get("yes_price", 0.5)
            resolution_date = state.get("resolution_date", "")
            probability_report = state.get("probability_report", "")
            prompt = f"""You are a Bear Analyst on a Polymarket prediction market. Your job is to argue that YES is overvalued at the current price; the market is mispriced high.

Market: "{market_question}"
Current YES price: {yes_price}  (range 0.0 to 1.0; this is the market's implied probability of YES)
Resolution date: {resolution_date}

Build the strongest evidence-based case that YES is overpriced. Ground your argument in:
1. Base rate: how often does this kind of event actually happen? Is the current price above the base rate?
2. Recent signals: what news, data, or developments favor a NO outcome?
3. Resolution criteria: are the criteria stricter than the market is pricing? Is there ambiguity that resolves toward NO?
4. Why the market is mispriced high: what is the crowd over-weighting? Recency bias, narrative momentum, or hype?
5. Bull Counterpoints: directly engage with the bull's claims; expose weak assumptions and over-optimism.

Avoid stock-market vocabulary (no P/E ratios, no earnings, no moats; this is a binary event contract).

Resources available:
News context for the event: {news_report}
Social/sentiment context: {sentiment_report}
Probability/base-rate analysis: {probability_report}
Market data report: {market_research_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}

Deliver a compelling bear argument and refute the bull's claims.
"""
        else:
            prompt = f"""You are a Bear Analyst making the case against investing in the stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the stock.
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
