from tradingagents.agents.utils.anonymization import anonymize_ticker
from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_risk_debate_summary,
)


def create_conservative_debator(llm, round_num=1):
    def conservative_node(state) -> dict:
        ticker = state["company_of_interest"]
        research_packet = build_research_packet(state)
        risk_summary = get_risk_debate_summary(state)
        trader_decision = state["trader_investment_plan"]

        # Anonymize data variables to prevent training-data bias
        anon_research_packet = anonymize_ticker(research_packet, ticker)
        anon_risk_summary = anonymize_ticker(risk_summary, ticker)
        anon_trader_decision = anonymize_ticker(trader_decision, ticker)

        if round_num == 1:
            prompt = f"""You are a Senior Risk Manager and Economist acting as the Conservative Risk Analyst. Your objective is to clinically identify systemic risks, volatility threats, and capital preservation requirements in the trader's plan.

Trader's Decision: {anon_trader_decision}

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective.
- Prioritize asset protection, volatility minimization, and tail-risk assessment.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.

CORE ANALYTICAL VECTORS:
1. **Risk Exposure**: Quantitative assessment of potential drawdowns and market volatility.
2. **Structural Fragility**: Identification of overlooked threats or unsustainable assumptions in the plan.

RESOURCES:
- Compressed Research: {anon_research_packet}
- Rolling Risk Summary: {anon_risk_summary}

Present your initial clinical position on the risk/reward profile. Build a data-driven case for why a conservative, risk-mitigating stance offers the best path forward.

Output in two sections:
1. THE DEBATE: Your initial clinical argument.
2. SUMMARY POINTS: 3 most critical risk/mitigation points.
"""
            response = llm.invoke(prompt)
            argument = f"Conservative Analyst (Round 1): {response.content}"
            return {"risk_r1_conservative": argument}

        else:
            # Round 2: read other analysts' R1 responses
            aggressive_r1 = state.get("risk_r1_aggressive", "")
            neutral_r1 = state.get("risk_r1_neutral", "")

            anon_aggressive_r1 = anonymize_ticker(aggressive_r1, ticker)
            anon_neutral_r1 = anonymize_ticker(neutral_r1, ticker)

            prompt = f"""You are a Senior Risk Manager and Economist acting as the Conservative Risk Analyst. Your objective is to clinically identify systemic risks, volatility threats, and capital preservation requirements in the trader's plan.

Trader's Decision: {anon_trader_decision}

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective.
- Prioritize asset protection, volatility minimization, and tail-risk assessment.
- Directly refute aggressive/neutral optimism using quantitative risk metrics and historical parallels.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.

CORE ANALYTICAL VECTORS:
1. **Risk Exposure**: Quantitative assessment of potential drawdowns and market volatility.
2. **Structural Fragility**: Identification of overlooked threats or unsustainable assumptions in the plan.
3. **Conservative Rebuttal**: State the single strongest data point from the opposing arguments. Then explain why your thesis holds despite it, using evidence from the research packet.

RESOURCES:
- Compressed Research: {anon_research_packet}
- Rolling Risk Summary: {anon_risk_summary}
- Aggressive analyst's position: {anon_aggressive_r1}
- Neutral analyst's position: {anon_neutral_r1}

Engage directly with their points. Highlight where their optimism may overlook risks and assert why a conservative stance is the safest path forward.

Output in two sections:
1. THE DEBATE: Your clinical rebuttal.
2. SUMMARY POINTS: 3 most critical risk/mitigation points.
"""
            response = llm.invoke(prompt)
            argument = f"Conservative Analyst (Round 2): {response.content}"
            return {"risk_r2_conservative": argument}

    return conservative_node
