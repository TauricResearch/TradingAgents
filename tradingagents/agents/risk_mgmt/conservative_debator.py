from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.anonymization import anonymize_ticker
from tradingagents.agents.utils.llm_guard import invoke_with_timeout, truncate_text
from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_risk_debate_summary,
)
from tradingagents.default_config import DEFAULT_CONFIG


def create_conservative_debator(
    llm: Any, round_num: int = 1
) -> Callable[[AgentState], dict[str, Any]]:
    def conservative_node(state: AgentState, /) -> dict[str, Any]:
        ticker = state["company_of_interest"]
        research_packet = build_research_packet(state)
        risk_summary = get_risk_debate_summary(state)
        trader_decision = state["trader_investment_plan"]

        # Anonymize data variables to prevent training-data bias
        anon_research_packet = anonymize_ticker(
            truncate_text(research_packet, max_chars=4500), ticker
        )
        anon_risk_summary = anonymize_ticker(truncate_text(risk_summary, max_chars=1600), ticker)
        anon_trader_decision = anonymize_ticker(
            truncate_text(trader_decision, max_chars=1800), ticker
        )
        _cap = float(DEFAULT_CONFIG.get("quick_think_llm_timeout_cap") or 300.0)
        timeout_seconds = min(
            float(
                DEFAULT_CONFIG.get("quick_think_llm_timeout")
                or DEFAULT_CONFIG.get("llm_timeout")
                or _cap
            ),
            _cap,
        )

        if round_num == 1:
            prompt = f"""You are a Senior Risk Manager and Economist acting as the Conservative Risk Analyst. Your objective is to clinically identify systemic risks, volatility threats, and capital preservation requirements in the trader's plan.

Trader's Decision: {anon_trader_decision}

STRICT CONSTRAINTS:
- Output only clinical, quantitative analysis in bullet points.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective.
- Prioritize asset protection, volatility minimization, and tail-risk assessment.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.
- **GROUND TRUTH**: The research packet contains a "Scanner Context (Phase 1)" section with verified commodity prices, FX rates, and calendar dates. Use ONLY those values. Do NOT invent, estimate, or contradict ground-truth figures. If you challenge the thesis, do so with logic, not fabricated numbers.

## EVIDENCE CITATION RULES (mandatory)

- Any numerical probability, rate, or statistical distribution you cite MUST appear in the analyst reports provided to you. Do NOT generate statistics from training data.
- If you want to express a probability or rate that is your own judgment (not from reports), preface it with: "Analyst estimate, unverified:"
- Hallucinated precision ("65% probability", "2.5 standard deviations") without a report source will be filtered. State your argument without false precision instead.

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
            response, invoke_error = invoke_with_timeout(
                llm,
                prompt,
                timeout_seconds=timeout_seconds,
                max_tokens=DEFAULT_CONFIG.get("quick_think_llm_max_tokens"),
            )
            if invoke_error is not None:
                if isinstance(invoke_error, TimeoutError):
                    response = AIMessage(
                        content=(
                            "THE DEBATE:\n"
                            "- Conservative analyst timeout fallback; no new downside expansion added this round.\n\n"
                            "SUMMARY POINTS:\n"
                            "- Preserve existing validated risk controls only.\n"
                            "- Do not add unsourced conservative claims.\n"
                            "- Escalate existing packet to synthesis."
                        )
                    )
                else:
                    raise invoke_error
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
- Output only clinical, quantitative analysis in bullet points.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective.
- Prioritize asset protection, volatility minimization, and tail-risk assessment.
- Directly refute aggressive/neutral optimism using quantitative risk metrics and historical parallels.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.
- **GROUND TRUTH**: The research packet contains a "Scanner Context (Phase 1)" section with verified commodity prices, FX rates, and calendar dates. Use ONLY those values. Do NOT invent, estimate, or contradict ground-truth figures.

## EVIDENCE CITATION RULES (mandatory)

- Any numerical probability, rate, or statistical distribution you cite MUST appear in the analyst reports provided to you. Do NOT generate statistics from training data.
- If you want to express a probability or rate that is your own judgment (not from reports), preface it with: "Analyst estimate, unverified:"
- Hallucinated precision ("65% probability", "2.5 standard deviations") without a report source will be filtered. State your argument without false precision instead.

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
            response, invoke_error = invoke_with_timeout(
                llm,
                prompt,
                timeout_seconds=timeout_seconds,
                max_tokens=DEFAULT_CONFIG.get("quick_think_llm_max_tokens"),
            )
            if invoke_error is not None:
                if isinstance(invoke_error, TimeoutError):
                    response = AIMessage(
                        content=(
                            "THE DEBATE:\n"
                            "- Conservative analyst rebuttal timed out; no new round-2 expansion added.\n\n"
                            "SUMMARY POINTS:\n"
                            "- Preserve prior conservative points only.\n"
                            "- Do not add unsourced rebuttals.\n"
                            "- Escalate existing debate state to synthesis."
                        )
                    )
                else:
                    raise invoke_error
            argument = f"Conservative Analyst (Round 2): {response.content}"
            return {"risk_r2_conservative": argument}

    return conservative_node
