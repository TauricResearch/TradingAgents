

def create_bull_researcher(llm):
    from tradingagents.agents.utils.agent_states import InstrumentType

    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        instrument_type = state.get("instrument_type", InstrumentType.STOCK.value)

        if instrument_type == InstrumentType.POLYMARKET.value:
            market_question = state.get("market_question", "")
            yes_price = state.get("yes_price", 0.5)
            resolution_date = state.get("resolution_date", "")
            probability_report = state.get("probability_report", "")
            prompt = f"""You are a Bull Analyst on a Polymarket prediction market. Your job is to argue that YES is undervalued at the current price and the market is mispriced.

Market: "{market_question}"
Current YES price: {yes_price}  (range 0.0 to 1.0; this is the market's implied probability of YES)
Resolution date: {resolution_date}

Build the strongest evidence-based case that YES is mispriced low. Ground your argument in:
1. Base rate: how often does this kind of event happen historically? Is the current price below the base rate?
2. Recent signals: what news, data, or developments favor YES outcome?
3. Resolution criteria: do the criteria favor a YES interpretation? Is there ambiguity that resolves toward YES?
4. Why the market is mispriced: what is the crowd missing? Information asymmetry, inattention, or systematic bias?
5. Bear Counterpoints: directly engage with the bear's claims; refute them with data and reasoning.

Avoid stock-market vocabulary (no P/E ratios, no earnings, no moats; this is a binary event contract).

Resources available:
News context for the event: {news_report}
Social/sentiment context: {sentiment_report}
Probability/base-rate analysis: {probability_report}
Market data report: {market_research_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}

Deliver a compelling bull argument and refute the bear's concerns.
"""
        else:
            prompt = f"""You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
"""

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
