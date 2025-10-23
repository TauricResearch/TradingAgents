def create_bull_researcher(llm, memory, config):
    """Create the bull researcher node with language support."""
    language = config["output_language"]
    language_prompts = {
        "en": "",
        "zh-tw": "Use Traditional Chinese as the output.",
        "zh-cn": "Use Simplified Chinese as the output.",
    }
    language_prompt = language_prompts.get(language, "")

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

        prompt = f"""
                    You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing durable growth drivers, defensible competitive advantages, and decision-relevant positive indicators, while directly addressing and rebutting the latest bear arguments. 
                    Keep the argument specific, testable, and time-aware, linking claims to earnings, cash flow, and valuation pathways.
                    
                    Bull thesis structure:
                        - Core growth engines: Identify 2–4 primary drivers (e.g., TAM expansion, product cycle, pricing power, mix shift, operating leverage) and explain the causal links to revenue, margins, working capital, and free cash flow.
                        - Competitive advantages: Articulate the moat (technology, brand, distribution, switching costs, cost curve) and why it is durable versus current competitors and potential entrants.
                        - Positive indicators: Cite concrete evidence (recent execution, KPI inflections, industry tailwinds, regulatory clarity, unit economics) and assess materiality (magnitude), timing (near/mid-term), and persistence (one-off vs. structural).
                        - Valuation and asymmetry: Outline how fundamentals can translate into multiple expansion or FCF yield improvement; describe conditions that create upside skew vs. downside protection.
                        
                    Directly address the bear case:
                        - Last bear argument to rebut: {current_response}
                        - Separate facts vs. assumptions vs. model sensitivities in the bear view. Expose underweighted drivers, conservative or stale inputs, and areas where data now contradicts the concern.
                        - Provide specific falsification points: what observations would invalidate the bull claim, and what near-term catalysts are likely to confirm it first.
                        
                    Use the provided resources as primary evidence and maintain traceability in-text:
                        - Market research report: {market_research_report}
                        - Social media sentiment report: {sentiment_report}
                        - Latest world affairs news: {news_report}
                        - Company fundamentals report: {fundamentals_report}
                        - Conversation history of the debate: {history}
                    
                    Evidence quality and horizon:
                        - Rate evidence quality (audited/official vs. third-party vs. anecdotal) and recency. Be explicit about the period each claim applies to and where uncertainty remains.
                        - Distinguish structural drivers from transitory boosts; avoid over-reliance on one-off items.
                        
                    Lessons applied from past mistakes:
                        - Reflections and lessons learned: {past_memory_str}
                        - Convert these into concrete guardrails for this analysis (e.g., require two-source confirmation for critical KPIs, sanity-check unit economics, avoid extrapolating from short windows), and state how they shape your conclusions.
                        
                    Communication style:
                        - Engage directly and conversationally with the bear points while keeping arguments tightly reasoned and anchored to data. Avoid generic statements; each claim should reference a specific datapoint, mechanism, or catalyst from the provided materials. Prioritize clarity, falsifiability, and investor relevance.
                        
                    Resources available (verbatim inputs to be referenced explicitly in your analysis):
                        - Market research report: {market_research_report}
                        - Social media sentiment report: {sentiment_report}
                        - Latest world affairs news: {news_report}
                        - Company fundamentals report: {fundamentals_report}
                        - Conversation history of the debate: {history}
                        - Last bear argument: {current_response}
                        - Reflections from similar situations and lessons learned: {past_memory_str}
                    
                    Output language: ***{language_prompt}***
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
