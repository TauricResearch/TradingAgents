"""Risk synthesis node — consolidates 2 rounds of parallel risk debate into a summary."""

from tradingagents.agents.utils.summary_context import build_research_packet


def create_risk_synthesis(llm):
    def risk_synthesis_node(state) -> dict:
        # Collect all round responses
        r1_agg = state.get("risk_r1_aggressive", "")
        r1_con = state.get("risk_r1_conservative", "")
        r1_neu = state.get("risk_r1_neutral", "")
        r2_agg = state.get("risk_r2_aggressive", "")
        r2_con = state.get("risk_r2_conservative", "")
        r2_neu = state.get("risk_r2_neutral", "")

        trader_decision = state.get("trader_investment_plan", "")
        research_packet = build_research_packet(state)

        # Build full history for Portfolio Manager
        history_parts = []
        if r1_agg:
            history_parts.append(r1_agg)
        if r1_con:
            history_parts.append(r1_con)
        if r1_neu:
            history_parts.append(r1_neu)
        if r2_agg:
            history_parts.append(r2_agg)
        if r2_con:
            history_parts.append(r2_con)
        if r2_neu:
            history_parts.append(r2_neu)

        full_history = "\n\n---\n\n".join(history_parts)

        prompt = f"""You are the Risk Synthesis Analyst. Two rounds of risk debate have concluded between Aggressive, Conservative, and Neutral analysts. Your task is to produce a concise, balanced synthesis.

**Trader's Plan:**
{trader_decision}

**Round 1 — Initial Positions:**

Aggressive: {r1_agg}

Conservative: {r1_con}

Neutral: {r1_neu}

**Round 2 — Rebuttals:**

Aggressive: {r2_agg}

Conservative: {r2_con}

Neutral: {r2_neu}

**Instructions:**
1. Identify the key points of agreement across all three analysts
2. Highlight the most critical points of disagreement
3. Assess which risk factors are most material to the trading decision
4. Provide a balanced risk assessment that weighs all perspectives
5. Flag any risks that ALL analysts agree on (these are highest conviction)

Output a structured risk synthesis in under 400 words."""

        response = llm.invoke(prompt)
        summary = response.content.strip()

        # Build risk_debate_state for Portfolio Manager backward compatibility
        risk_debate_state = {
            "history": full_history,
            "summary": summary,
            "aggressive_history": (r1_agg + "\n\n" + r2_agg) if r1_agg else "",
            "conservative_history": (r1_con + "\n\n" + r2_con) if r1_con else "",
            "neutral_history": (r1_neu + "\n\n" + r2_neu) if r1_neu else "",
            "latest_speaker": "Synthesis",
            "current_aggressive_response": r2_agg or r1_agg,
            "current_conservative_response": r2_con or r1_con,
            "current_neutral_response": r2_neu or r1_neu,
            "judge_decision": "",
            "count": 6,  # 3 per round x 2 rounds
        }

        return {
            "risk_debate_state": risk_debate_state,
            "sender": "risk_synthesis",
        }

    return risk_synthesis_node
