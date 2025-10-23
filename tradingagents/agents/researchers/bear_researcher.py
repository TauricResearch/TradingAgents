def create_bear_researcher(llm, memory, config):
    """Create the bear researcher node with language support."""
    language = config["output_language"]
    language_prompts = {
        "en": "",
        "zh-tw": "Use Traditional Chinese as the output.",
        "zh-cn": "Use Simplified Chinese as the output.",
    }
    language_prompt = language_prompts.get(language, "")

    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_analysis"]
        sentiment_analysis = state["sentiment_analysis"]
        news_analysis = state["news_analysis"]
        fundamentals_analysis = state["fundamentals_analysis"]

        curr_situation = f"{market_research_report}\n\n{sentiment_analysis}\n\n{news_analysis}\n\n{fundamentals_analysis}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""
You are a Bear Analyst making the case against investing in the stock. 
Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. 
Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:
Market research report: 
{market_research_report}


--------------------------------------
Social media sentiment report: 
{sentiment_analysis}


--------------------------------------
Latest world affairs news: 
{news_analysis}


--------------------------------------
Company fundamentals report: 
{fundamentals_analysis}


--------------------------------------
Conversation history of the debate: 
{history}


--------------------------------------
Last bull argument: 
{current_response}


--------------------------------------
Reflections from similar situations and lessons learned: 
{past_memory_str}


--------------------------------------
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the stock. 
You must also address reflections and learn from lessons and mistakes you made in the past.

Output language: ***{language_prompt}***
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
