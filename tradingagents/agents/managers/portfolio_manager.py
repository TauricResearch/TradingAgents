from tradingagents.agents.utils.agent_utils import build_instrument_context


def create_portfolio_manager(llm, memory):
    def portfolio_manager_node(state) -> dict:

        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]
        macro_regime_report = state.get("macro_regime_report", "")

        # Check for critical abort in market_report or fundamentals_report
        is_critical_abort = (
            "[CRITICAL ABORT]" in market_research_report or
            "[CRITICAL ABORT]" in fundamentals_report
        )

        # Build current situation with all reports
        macro_section = f"\n\nMacro Regime:\n{macro_regime_report}" if macro_regime_report else ""
        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}{macro_section}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        macro_context = f"\n\nCurrent Macro Regime:\n{macro_regime_report}\nEnsure your risk assessment reflects the macro environment — in risk-off regimes, apply higher standards for position entry and tighter risk controls.\n" if macro_regime_report else ""

        # Build prompt based on whether this is a critical abort scenario
        if is_critical_abort:
            # Critical abort: Use the aborting analyst's report and recommend SELL/AVOID
            abort_report = market_research_report if "[CRITICAL ABORT]" in market_research_report else fundamentals_report
            
            prompt = f"""As the Portfolio Manager, you have received a critical abort signal from an early analyst. This indicates catastrophic conditions (bankruptcy, SEC delisting, etc.) that require immediate action.

{instrument_context}

---

**CRITICAL ABORT DETECTED**

**Aborting Analyst's Report:**
{abort_report}

**Context:**
- Trader's proposed plan: **{trader_plan}**
- Lessons from past decisions: **{past_memory_str}**

**Required Output Structure:**
1. **Rating**: State one of Buy / Overweight / Hold / Underweight / Sell.
2. **Executive Summary**: A concise action plan covering entry strategy, position sizing, key risk levels, and time horizon.
3. **Investment Thesis**: Detailed reasoning based on the critical abort signal and the aborting analyst's report.

---

**IMPORTANT**: Based on the critical abort signal, you should recommend SELL or AVOID. Do not proceed with any other analysis. The aborting analyst has identified fundamental issues that make this investment unacceptable."""

            response = llm.invoke(prompt)
        else:
            # Normal flow: Synthesize all reports and make decision
            prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.
{macro_context}

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Trader's proposed plan: **{trader_plan}**
- Lessons from past decisions: **{past_memory_str}**

**Required Output Structure:**
1. **Rating**: State one of Buy / Overweight / Hold / Underweight / Sell.
2. **Executive Summary**: A concise action plan covering entry strategy, position sizing, key risk levels, and time horizon.
3. **Investment Thesis**: Detailed reasoning anchored in the analysts' debate and past reflections.

---

**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts."""

            response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return portfolio_manager_node
