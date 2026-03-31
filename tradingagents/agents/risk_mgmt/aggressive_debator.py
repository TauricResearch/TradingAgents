from tradingagents.agents.utils.anonymization import anonymize_ticker
from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_risk_debate_summary,
)


def create_aggressive_debator(llm, round_num=1):
    def aggressive_node(state) -> dict:
        ticker = state["company_of_interest"]
        research_packet = build_research_packet(state)
        risk_summary = get_risk_debate_summary(state)
        trader_decision = state["trader_investment_plan"]

        # Anonymize data variables to prevent training-data bias
        anon_research_packet = anonymize_ticker(research_packet, ticker)
        anon_risk_summary = anonymize_ticker(risk_summary, ticker)
        anon_trader_decision = anonymize_ticker(trader_decision, ticker)

        if round_num == 1:
            prompt = f"""You are a Senior Quantitative Strategist acting as the Aggressive Risk Analyst. Your objective is to clinically analyze high-reward, high-risk opportunities in the trader's plan, focusing on growth deltas and competitive moats.

Trader's Decision: {anon_trader_decision}

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective.
- Identify specific asymmetric upside opportunities and innovative benefits.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.

CORE ANALYTICAL VECTORS:
1. **Upside Delta**: Quantitative analysis of potential growth and innovative benefits.
2. **Moat Validation**: Evidence of structural advantages that justify elevated risk.

RESOURCES:
- Compressed Research: {anon_research_packet}
- Rolling Risk Summary: {anon_risk_summary}

Present your initial clinical position on the risk/reward profile. Build a data-driven case for why the aggressive stance offers the best path forward.

Output in two sections:
1. THE DEBATE: Your initial clinical argument.
2. SUMMARY POINTS: 3 most critical risk/reward points.
"""
            response = llm.invoke(prompt)
            argument = f"Aggressive Analyst (Round 1): {response.content}"
            return {"risk_r1_aggressive": argument}

        else:
            # Round 2: read other analysts' R1 responses
            conservative_r1 = state.get("risk_r1_conservative", "")
            neutral_r1 = state.get("risk_r1_neutral", "")

            anon_conservative_r1 = anonymize_ticker(conservative_r1, ticker)
            anon_neutral_r1 = anonymize_ticker(neutral_r1, ticker)

            prompt = f"""You are a Senior Quantitative Strategist acting as the Aggressive Risk Analyst. Your objective is to clinically analyze high-reward, high-risk opportunities in the trader's plan, focusing on growth deltas and competitive moats.

Trader's Decision: {anon_trader_decision}

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective.
- Identify specific asymmetric upside opportunities and innovative benefits.
- Directly refute conservative/neutral points using hard data and quantitative reasoning.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.

CORE ANALYTICAL VECTORS:
1. **Upside Delta**: Quantitative analysis of potential growth and innovative benefits.
2. **Moat Validation**: Evidence of structural advantages that justify elevated risk.
3. **Aggressive Rebuttal**: State the single strongest data point from the opposing arguments. Then explain why your thesis holds despite it, using evidence from the research packet.

RESOURCES:
- Compressed Research: {anon_research_packet}
- Rolling Risk Summary: {anon_risk_summary}
- Conservative analyst's position: {anon_conservative_r1}
- Neutral analyst's position: {anon_neutral_r1}

Engage directly with their points. Refute weaknesses in their logic and assert why a high-risk approach is optimal.

Output in two sections:
1. THE DEBATE: Your clinical rebuttal.
2. SUMMARY POINTS: 3 most critical risk/reward points.
"""
            response = llm.invoke(prompt)
            argument = f"Aggressive Analyst (Round 2): {response.content}"
            return {"risk_r2_aggressive": argument}

    return aggressive_node
