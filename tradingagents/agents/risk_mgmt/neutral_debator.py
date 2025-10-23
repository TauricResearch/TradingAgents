def create_neutral_debator(llm, config):
    """Create the neutral debator node with language support."""
    language = config["output_language"]
    language_prompts = {
        "en": "",
        "zh-tw": "Use Traditional Chinese as the output.",
        "zh-cn": "Use Simplified Chinese as the output.",
    }
    language_prompt = language_prompts.get(language, "")

    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_safe_response = risk_debate_state.get("current_safe_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""
                    As the Neutral Risk Analyst, provide a balanced, evidence-led perspective that weighs potential benefits against risks, and proposes a moderate, sustainable adjustment to the trader’s plan when warranted. 
                    Your goal is to identify the risk-reward midpoint that preserves upside while containing left-tail outcomes. 
                    Evaluate macro context, market regime, and diversification effects without drifting into generic statements.
                    
                    Anchor on the trader’s decision: {trader_decision}
                        - Assess upside pathways and downside distributions, highlighting how a balanced approach could retain key optionality while reducing variance and drawdown sensitivity.
                        
                    Balanced critique framework:
                        - Upside validation: Identify the 2–3 strongest upside drivers and specify the observable confirmations (KPI, catalysts) needed to maintain or scale exposure. Explain causal links to earnings, cash flow, and valuation.
                        - Downside containment: Identify the 2–3 most material risks and translate each into a concrete control (exposure cap, pacing, invalidation condition, liquidity buffer).
                        - Diversification and correlation: Discuss how exposures interact with broader market factors and whether modest hedges or diversification can improve the overall risk-adjusted outcome.
                        
                    Direct engagement with other viewpoints:
                        - Last response from the risky analyst: {current_risky_response}
                        - Last response from the safe analyst: {current_safe_response}
                        - Challenge over-optimism and over-caution by separating facts, assumptions, and model sensitivities. Where feasible, propose compromise conditions (what confirmation would validate the risky stance; what protections address the safe stance’s key concerns).
                        
                    Traceable evidence base:
                        - Market Research Report: {market_research_report}
                        - Social Media Sentiment Report: {sentiment_report}
                        - Latest World Affairs Report: {news_report}
                        - Company Fundamentals Report: {fundamentals_report}
                        - Conversation history for context and citations: {history}
                        
                    Neutral adjustment proposal (analytical):
                        - Position calibration: suggest a moderate exposure profile with clear conditions to scale up on confirmation or de‑risk on deterioration.
                        - Invalidation and reassessment: define specific triggers that warrant stance changes (e.g., KPI misses/beats, guidance shifts, spread/volatility regime changes).
                        - Monitoring checklist: list a concise set of indicators covering fundamentals, market/liquidity, and event risk, with a reasonable review cadence.
                        
                    Communication style:
                        - Be conversational yet precise. Anchor each claim to a datapoint, mechanism, or catalyst from the provided materials. Avoid generic language; make the trade‑offs explicit and testable.
                        
                    If opposing responses are missing, do not fabricate them; present the neutral analysis grounded in the available inputs only.
                    
                    Output language: ***{language_prompt}***
                """

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_risky_response": risk_debate_state.get(
                "current_risky_response", ""
            ),
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
