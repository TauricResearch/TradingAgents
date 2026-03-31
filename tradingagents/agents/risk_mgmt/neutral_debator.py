from tradingagents.agents.utils.anonymization import anonymize_ticker
from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_risk_debate_summary,
)


def create_neutral_debator(llm, round_num=1):
    def neutral_node(state) -> dict:
        ticker = state["company_of_interest"]
        research_packet = build_research_packet(state)
        risk_summary = get_risk_debate_summary(state)
        trader_decision = state["trader_investment_plan"]

        # Anonymize data variables to prevent training-data bias
        anon_research_packet = anonymize_ticker(research_packet, ticker)
        anon_risk_summary = anonymize_ticker(risk_summary, ticker)
        anon_trader_decision = anonymize_ticker(trader_decision, ticker)

        if round_num == 1:
            prompt = f"""You are a Senior Portfolio Strategist acting as the Neutral Risk Analyst. Your objective is to provide a clinically balanced assessment of the trader's plan, weighing growth potential against risk constraints.

Trader's Decision: {anon_trader_decision}

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective.
- Prioritize objective synthesis, diversification benefits, and regime alignment.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.

CORE ANALYTICAL VECTORS:
1. **Balanced Delta**: Quantitative analysis of trade-offs between growth and stability.
2. **Diversification Efficacy**: Assessment of how the plan fits broader portfolio and market trends.

RESOURCES:
- Compressed Research: {anon_research_packet}
- Rolling Risk Summary: {anon_risk_summary}

Present your initial balanced position on the risk/reward profile. Build a data-driven case for why a moderate, balanced approach offers the most reliable path forward.

Output in two sections:
1. THE DEBATE: Your initial clinical argument.
2. SUMMARY POINTS: 3 most critical balanced risk/reward points.
"""
            response = llm.invoke(prompt)
            argument = f"Neutral Analyst (Round 1): {response.content}"
            return {"risk_r1_neutral": argument}

        else:
            # Round 2: read other analysts' R1 responses
            aggressive_r1 = state.get("risk_r1_aggressive", "")
            conservative_r1 = state.get("risk_r1_conservative", "")

            anon_aggressive_r1 = anonymize_ticker(aggressive_r1, ticker)
            anon_conservative_r1 = anonymize_ticker(conservative_r1, ticker)

            prompt = f"""You are a Senior Portfolio Strategist acting as the Neutral Risk Analyst. Your objective is to provide a clinically balanced assessment of the trader's plan, weighing growth potential against risk constraints.

Trader's Decision: {anon_trader_decision}

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective.
- Prioritize objective synthesis, diversification benefits, and regime alignment.
- Critique both aggressive and conservative positions for data gaps or extreme biases.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.

CORE ANALYTICAL VECTORS:
1. **Balanced Delta**: Quantitative analysis of trade-offs between growth and stability.
2. **Diversification Efficacy**: Assessment of how the plan fits broader portfolio and market trends.
3. **Neutral Rebuttal**: State the single strongest data point from the opposing arguments. Then explain why your thesis holds despite it, using evidence from the research packet.

RESOURCES:
- Compressed Research: {anon_research_packet}
- Rolling Risk Summary: {anon_risk_summary}
- Aggressive analyst's position: {anon_aggressive_r1}
- Conservative analyst's position: {anon_conservative_r1}

Engage directly with their points. Challenge both extremes and assert why a balanced, moderate approach offers the best of both worlds.

Output in two sections:
1. THE DEBATE: Your clinical rebuttal.
2. SUMMARY POINTS: 3 most critical balanced risk/reward points.
"""
            response = llm.invoke(prompt)
            argument = f"Neutral Analyst (Round 2): {response.content}"
            return {"risk_r2_neutral": argument}

    return neutral_node
