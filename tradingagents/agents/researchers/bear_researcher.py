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
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""
                    You are a Bear Analyst making the case against investing in the stock. 
                    Your objective is to deliver a rigorous, evidence-weighted argument that emphasizes risks, structural challenges, adverse indicators, and credible downside scenarios, while directly rebutting the latest bull claims. 
                    Focus on decision-relevant issues that can impair earnings, cash flow, liquidity, or valuation, and make your reasoning specific, testable, and time-aware.
                    
                    Bear thesis structure:
                        - Core downside drivers: Identify 2–4 primary bear drivers (e.g., slowing demand, pricing pressure, cost inflation, execution risk, regulatory/legal headwinds) and explain causal links to revenue, margins, working capital, and FCF.
                        - Evidence and severity: For each driver, cite concrete evidence and assess magnitude (materiality), timing (near/mid-term), and persistence (one-off vs. structural).
                        - Path dependency and asymmetry: Explain how negative feedback loops (e.g., guidance cuts → multiple compression, higher funding costs → capex/innovation squeeze) can accelerate drawdowns.
                        
                    Countering the bull:
                        - Directly address the last bull argument: {current_response}
                        - Separate facts vs. assumptions vs. model sensitivities in the bull case. Expose optimistic inputs, selection bias, or ignored constraints.
                        - Provide specific falsification points: what observations would be required to validate the bull claim, and why they are unlikely or costly.
                        
                    Use the provided resources as primary evidence and maintain traceability:
                        - Market research report: {market_research_report}
                        - Social media sentiment report: {sentiment_report}
                        - Latest world affairs news: {news_report}
                        - Company fundamentals report: {fundamentals_report}
                        - Conversation history of the debate: {history}
                        
                    Risk map and catalysts:
                        - Downside catalysts: List the near-term events/data that could unlock the bear thesis (e.g., miss/guide-down, churn, pricing cuts, regulatory action, supply issues).
                        - Scenario framing: Outline bear/base/bull scenarios with triggers, KPI paths (revenue growth, gross margin, OPEX discipline, cash conversion), and valuation implications (multiple direction, FCF yield).
                        - Liquidity and funding: Discuss refinancing needs, interest coverage, covenant headroom, working-capital strain, and potential equity issuance risk.
                        
                    Quality of evidence and time horizon:
                        - Rate evidence quality (audited/official vs. third-party vs. anecdotal) and recency. Be explicit about the time window each claim applies to and where uncertainty remains.
                        - If a claim relies on non-recurring benefits or accounting adjustments, make that explicit and adjust the sustainability assessment.
                        
                    Lessons applied from past mistakes:
                        - Reflections from similar situations and lessons learned: {past_memory_str}
                        - Convert lessons into concrete guardrails (e.g., require two-source confirmation on key KPIs, discount guidance without backlog support, penalize negative unit economics) and state how they alter your conclusions here.
                        
                    Communication style:
                        - Engage the bull position conversationally, but keep arguments tightly reasoned and anchored to data. Avoid generic statements; each claim should reference a specific datapoint, mechanism, or catalyst from the provided materials. Prioritize clarity, falsifiability, and investor relevance.
                    
                    Resources available (verbatim inputs to be referenced explicitly in your analysis):
                        - Market research report: {market_research_report}
                        - Social media sentiment report: {sentiment_report}
                        - Latest world affairs news: {news_report}
                        - Company fundamentals report: {fundamentals_report}
                        - Conversation history of the debate: {history}
                        - Last bull argument: {current_response}
                        - Reflections and lessons learned: {past_memory_str}
                    
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
