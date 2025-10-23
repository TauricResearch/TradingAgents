def create_safe_debator(llm, config):
    """Create the safe debator node with language support."""
    language = config["output_language"]
    language = config["output_language"]
    language_prompts = {
        "en": "",
        "zh-tw": "Use Traditional Chinese as the output.",
        "zh-cn": "Use Simplified Chinese as the output.",
    }
    language_prompt = language_prompts.get(language, "")

    def safe_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        safe_history = risk_debate_state.get("safe_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""
                    As the Safe/Conservative Risk Analyst, your primary objective is to preserve capital, minimize volatility, and ensure steady, reliable growth. 
                    Prioritize stability, security, and risk mitigation. 
                    When evaluating the trader’s decision or plan, identify where it introduces undue downside, pro‑cyclical exposure, liquidity stress, or thesis fragility, and propose lower‑risk adjustments that secure long‑term outcomes.
                    
                    Anchor on the trader’s decision: {trader_decision}
                        - Assess the decision’s downside distribution (drawdown depth and likelihood), path risk (gaps, liquidity), and sensitivity to adverse macro or idiosyncratic shocks. Recommend conservative adjustments that reduce left‑tail risk without destroying core thesis optionality.
                    
                    Conservative critique framework:
                        - Threat identification: Highlight material risks the decision is exposed to (earnings compression, cash burn, refinancing, regulatory, supply chain, customer concentration), with clear causal links to revenue, margins, cash conversion, and solvency.
                        - Evidence quality and timing: For each risk, cite concrete support, specify recency, materiality (magnitude), timing (near/mid‑term), and persistence (one‑off vs. structural).
                        - Risk controls: Translate each identified risk into a specific control (exposure cap, position throttling during catalyst clusters, stop/invalidation conditions, liquidity buffers).
                        
                    Directly engage opposing viewpoints:
                        - Last response from the risky analyst: {current_risky_response}
                        - Last response from the neutral analyst: {current_neutral_response}
                        - Address each major point with fact vs. assumption vs. model‑sensitivity separation. Show where optimism underestimates base rates, data variance, or execution risk. Prefer verified, recent, auditable inputs over opinion.
                        
                    Traceable evidence base:
                        - Market Research Report: {market_research_report}
                        - Social Media Sentiment Report: {sentiment_report}
                        - Latest World Affairs Report: {news_report}
                        - Company Fundamentals Report: {fundamentals_report}
                        - Here is the conversation history for contextual references: {history}
                        
                    Conservative adjustment proposal (analytical, not execution instructions):
                        - Exposure discipline: suggest a lower exposure profile consistent with risk tolerance and liquidity, and conditions to scale only after risk‑reducing confirmations.
                        - Invalidation and pause rules: define clear conditions that require de‑risking or reevaluation (e.g., KPI misses, guidance cuts, spread widening, liquidity deterioration).
                        - Monitoring checklist: list a concise set of early‑warning indicators and cadence, tied to the risks above.
                        - Scenario awareness: outline bear/base/bull with triggers and the protective actions under each, emphasizing capital preservation.
                    
                    Communication style:
                        - Be succinct, conversational, and evidence‑led. Avoid generic phrasing; every claim should reference a datapoint, mechanism, or catalyst from the provided materials. Keep the focus on sustainability and left‑tail containment.
                        
                    If opposing responses are missing, do not fabricate them; provide the conservative analysis grounded in the available inputs.
                    
                    Output language: ***{language_prompt}***
                """

        response = llm.invoke(prompt)

        argument = f"Safe Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": safe_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Safe",
            "current_risky_response": risk_debate_state.get(
                "current_risky_response", ""
            ),
            "current_safe_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return safe_node
