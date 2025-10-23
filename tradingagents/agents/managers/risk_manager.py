def create_risk_manager(llm, memory, config):
    """Create the risk manager node with language support."""
    language = config["output_language"]
    language_prompts = {
        "en": "",
        "zh-tw": "Use Traditional Chinese as the output.",
        "zh-cn": "Use Simplified Chinese as the output.",
    }
    language_prompt = language_prompts.get(language, "")

    def risk_manager_node(state) -> dict:
        company_name = state["company_of_interest"]

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["news_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""
                    Acting as the Risk Management Judge and Debate Facilitator, evaluate the debate between the three risk analysts—Risky, Neutral, and Safe/Conservative—and produce a single, decisive recommendation: Buy, Sell, or Hold. 
                    Do not select Hold as a compromise; choose Hold only when key uncertainties are imminent, material, and make the risk-reward effectively flat with no near-term disambiguation.
                    
                    Guidelines for decision-making:
                        1. Summarize key arguments:
                            - Extract the strongest points from each analyst that directly affect risk exposure, drawdown potential, probability of loss, liquidity, and path dependency.
                            - Distinguish facts, assumptions, and model-based inferences. Note time sensitivity and how each point could be falsified or confirmed.
                        2. Provide rationale with anchored evidence:
                            - Support the recommendation using specific arguments from the debate; when relevant, reference exact claims to show how they alter downside tails, variance, and left-skew risk.
                            - Explicitly state what observations would reverse the stance (clear invalidation conditions).
                        3. Refine the trader’s plan:
                            - Start from the trader’s original plan: {trader_plan}
                            - Adjust entries/exits, sizing logic, and guardrails to ensure downside protection under adverse scenarios presented in the debate.
                        4. Learn from past mistakes:
                            - Use lessons from: {past_memory_str}
                            - Translate reflections into concrete guardrails (e.g., two-source confirmation for critical inputs, maximum single-trade loss cap, pre-specified stop discipline) and state exactly how they apply now to avoid a wrong BUY/SELL/HOLD call.
                            
                    Deliverables:
                        - Recommendation (BUY / SELL / HOLD) placed at the very beginning of the response.
                        - Risk-based rationale: concise, evidence-weighted explanation tying the decision to the debate’s most decision-relevant points and their impact on loss distribution.
                        - Risk plan adjustments:
                            - Entry/exit conditions and invalidation levels.
                            - Position sizing rules linked to volatility or risk budget (e.g., reduce sizing when uncertainty widens or catalysts cluster).
                            - Drawdown guardrails (max loss per position/session), and contingency actions under gap risk or liquidity deterioration.
                            - Monitoring checklist: list the top triggers and early-warning indicators that would prompt de-risking or re-assessment.
                            
                    Analysts Debate History:
                    {history}

                    Output style:
                    Focus on actionable risk insights and continuous improvement. Be specific, testable, and time-aware. Avoid generic phrasing; each claim should have a verifying observation, trigger, or control action.

                    Output language: ***{language_prompt}***
                """

        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "risky_history": risk_debate_state["risky_history"],
            "safe_history": risk_debate_state["safe_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_risky_response": risk_debate_state["current_risky_response"],
            "current_safe_response": risk_debate_state["current_safe_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return risk_manager_node
