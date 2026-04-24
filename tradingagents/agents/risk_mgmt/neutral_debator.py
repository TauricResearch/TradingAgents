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


def create_neutral_debator(llm: Any, round_num: int = 1) -> Callable[[AgentState], dict[str, Any]]:
    def neutral_node(state: AgentState) -> dict[str, Any]:
        ticker = state["company_of_interest"]
        research_packet = build_research_packet(state)
        risk_summary = get_risk_debate_summary(state)
        trader_decision = state["trader_investment_plan"]

        # Anonymize data variables to prevent training-data bias
        anon_research_packet = anonymize_ticker(
            truncate_text(research_packet, max_chars=4500), ticker
        )
        anon_risk_summary = anonymize_ticker(
            truncate_text(risk_summary, max_chars=1600), ticker
        )
        anon_trader_decision = anonymize_ticker(
            truncate_text(trader_decision, max_chars=1800), ticker
        )
        _cap = float(DEFAULT_CONFIG.get("quick_think_llm_timeout_cap") or 300.0)
        timeout_seconds = min(
            float(DEFAULT_CONFIG.get("quick_think_llm_timeout") or DEFAULT_CONFIG.get("llm_timeout") or _cap),
            _cap,
        )

        if round_num == 1:
            prompt = f"""You are a Senior Portfolio Strategist acting as the Neutral Risk Analyst. Your objective is to provide a clinically balanced assessment of the trader's plan, weighing growth potential against risk constraints.

Trader's Decision: {anon_trader_decision}

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY, X.Xbps. No superlatives ("massive", "huge", "significant"). Every claim must reference a specific number, date, or source.
- NO conversational filler, roleplay, or first-person perspective.
- Prioritize objective synthesis, diversification benefits, and regime alignment.
- CONFIDENCE: Append (HIGH/MED/LOW) to each claim based on data recency and source quality. HIGH = verified from pre-loaded data or tools. MED = inferred from partial evidence. LOW = directional estimate.
- **GROUND TRUTH**: The research packet contains a "Scanner Context (Phase 1)" section with verified commodity prices, FX rates, and calendar dates. Use ONLY those values. Do NOT invent, estimate, or contradict ground-truth figures. If you challenge the thesis, do so with logic, not fabricated numbers.

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
            response, invoke_error = invoke_with_timeout(
                llm, prompt, timeout_seconds=timeout_seconds, max_tokens=DEFAULT_CONFIG.get("quick_think_llm_max_tokens")
            )
            if invoke_error is not None:
                if isinstance(invoke_error, TimeoutError):
                    response = AIMessage(
                        content=(
                            "THE DEBATE:\n"
                            "- Neutral analyst timeout fallback; no new balanced expansion added this round.\n\n"
                            "SUMMARY POINTS:\n"
                            "- Preserve existing validated balance arguments only.\n"
                            "- Do not add unsourced neutral claims.\n"
                            "- Escalate existing packet to synthesis."
                        )
                    )
                else:
                    raise invoke_error
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
- **GROUND TRUTH**: The research packet contains a "Scanner Context (Phase 1)" section with verified commodity prices, FX rates, and calendar dates. Use ONLY those values. Do NOT invent, estimate, or contradict ground-truth figures.

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
            response, invoke_error = invoke_with_timeout(
                llm, prompt, timeout_seconds=timeout_seconds, max_tokens=DEFAULT_CONFIG.get("quick_think_llm_max_tokens")
            )
            if invoke_error is not None:
                if isinstance(invoke_error, TimeoutError):
                    response = AIMessage(
                        content=(
                            "THE DEBATE:\n"
                            "- Neutral analyst rebuttal timed out; no new round-2 expansion added.\n\n"
                            "SUMMARY POINTS:\n"
                            "- Preserve prior neutral points only.\n"
                            "- Do not add unsourced rebuttals.\n"
                            "- Escalate existing debate state to synthesis."
                        )
                    )
                else:
                    raise invoke_error
            argument = f"Neutral Analyst (Round 2): {response.content}"
            return {"risk_r2_neutral": argument}

    return neutral_node
