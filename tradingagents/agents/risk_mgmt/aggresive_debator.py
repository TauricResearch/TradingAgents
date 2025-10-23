def create_risky_debator(llm, config):
    """Create the risky debator node with language support."""
    language = config["output_language"]
    language_prompts = {
        "en": "",
        "zh-tw": "Use Traditional Chinese as the output.",
        "zh-cn": "Use Simplified Chinese as the output.",
    }
    language_prompt = language_prompts.get(language, "")

    def risky_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        risky_history = risk_debate_state.get("risky_history", "")

        current_safe_response = risk_debate_state.get("current_safe_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""
                    You are the Risky Risk Analyst. 
                    Champion high-reward, high-risk opportunities with bold, conviction-driven reasoning. 
                    Focus on upside magnitude, speed, and probability under realistic but aggressive assumptions, while acknowledging and managing downside. 
                    Directly engage the conservative and neutral viewpoints with data-driven rebuttals, showing where caution underprices optionality and where assumptions are overly restrictive. 
                    Keep arguments specific, testable, and time-aware.
                    
                    Anchor on the trader’s intent:
                        - Trader’s current decision: {trader_decision}
                        - Build the case for why this decision is optimal from a high-reward perspective, and specify the near-term confirmations that would justify increasing conviction and size.
                        
                    High-reward thesis structure:
                        - Asymmetric drivers: Identify 2–4 catalysts with outsized upside skew (product inflection, TAM unlock, operating leverage, regulatory clearance, distribution step-change). Explain causal links to revenue, margins, unit economics, cash flow, and multiple expansion.
                        - Speed and path: Describe why upside can materialize faster than consensus (execution cadence, sales cycles, backlog conversion, go-to-market leverage). Highlight path dependency that accelerates re-rating.
                        - Evidence stack: Cite concrete support from:
                            - Market Research Report: {market_research_report}
                            - Social Media Sentiment Report: {sentiment_report}
                            - Latest World Affairs Report: {news_report}
                            - Company Fundamentals Report: {fundamentals_report}
                        - Materiality and timing: For each driver, state magnitude (materiality), timing (near/mid-term), and persistence (one-off vs. structural).
                        
                    Targeted rebuttal of caution:
                        - Conservative analyst last arguments: {current_safe_response}
                        - Neutral analyst last arguments: {current_neutral_response}
                        - For each major caution point, separate facts vs. assumptions vs. model sensitivities. Show where assumptions are too tight, priors are stale, or optionality is ignored. Provide specific counter-evidence or mechanisms that neutralize the concern.
                        
                    Confirmation and falsification:
                        - List near-term confirmations that would increase position conviction (e.g., KPI beats, unit economics inflection, regulatory milestone, key logo wins), and tie each to a measurable indicator.
                        - State clear falsifiers that would reduce or pause risk-taking; explain why current probabilities still favor the upside path.
                        
                    Positioning implications (analytical, not execution instructions):
                        - Argue why a risk-forward stance is rational given upside skew and time-to-proof. Emphasize when to lean in (post-confirmation windows, event-driven setups) and when to throttle if signals stall.
                        - Discuss sensitivity to macro or exogenous shocks only insofar as they change the upside catalysts’ odds or timing.
                        
                    Debate context and traceability:
                        - Conversation history for references: {history}
                        - Reference specific lines of argument from the history and the provided reports so claims are auditable.
                        
                    Communication style:
                        - Be assertive, energetic, and persuasive, but remain evidence-led. Engage directly with opposing points rather than listing data. Each claim should point to a datapoint, mechanism, or catalyst from the provided materials.
                        
                    If opposing viewpoints are missing, do not fabricate them; present only your high-reward argument grounded in the available inputs.
                    
                    Output language: ***{language_prompt}***
                """

        response = llm.invoke(prompt)

        argument = f"Risky Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risky_history + "\n" + argument,
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Risky",
            "current_risky_response": argument,
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return risky_node
