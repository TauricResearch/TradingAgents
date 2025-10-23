def create_research_manager(llm, memory, config):
    """Create the research manager node with language support."""
    language = config["output_language"]
    language_prompts = {
        "en": "",
        "zh-tw": "Use Traditional Chinese as the output.",
        "zh-cn": "Use Simplified Chinese as the output.",
    }
    language_prompt = language_prompts.get(language, "")

    def research_manager_node(state) -> dict:
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""
                    As the portfolio manager and debate facilitator, your role is to critically evaluate this round of debate and make a definitive decision: align with the bear analyst, the bull analyst, or choose Hold only if it is strongly justified based on the arguments presented. 
                    Do not default to Hold as a compromise; choose it only when key uncertainties are imminent, material, and make risk-reward effectively flat.
                    Summarize the key points from both sides concisely, focusing on the most compelling evidence or reasoning. 
                    Distinguish facts, assumptions, and model-based inferences, and note data quality and near-term catalysts where relevant. 
                    Your recommendation—Buy, Sell, or Hold—must be clear, testable, and actionable.
                    
                    Decision rules:
                        - Prefer recent, verifiable, and causally linked evidence over opinions or stale metrics.
                        - Favor arguments that map directly to earnings, cash flow, liquidity, or competitive position with identifiable triggers.
                        - State what observations would flip your stance (reversal conditions) and why.
                        
                    Your deliverables:
                        - Your Recommendation: BUY / SELL / HOLD (place this at the very beginning of your response).
                        - Rationale: A concise explanation tying the stance to the strongest debate arguments and catalysts.
                        - Strategic Actions: Concrete steps for implementing the recommendation, including entry/timing triggers, scaling rules on confirmation/failure, and clear invalidation conditions.
                        - Key Uncertainties: The 2–4 most important unknowns that could change the stance, plus how they will be monitored.
                        
                    Use your past mistakes to adjust this decision. Extract concrete guardrails from the reflections and state exactly how they are applied here.

                    Here are your past reflections on mistakes:
                    "{past_memory_str}"

                    Here is the debate:
                    Debate History:
                    {history}

                    Output language: ***{language_prompt}***
                """
        response = llm.invoke(prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
