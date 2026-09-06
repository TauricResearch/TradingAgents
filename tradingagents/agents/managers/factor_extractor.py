"""Factor Extractor: the "structured" decision_mode's replacement for the
Bull/Bear Researcher debate + Research Manager synthesis (trading-workspace
TradingAgents#19).

One LLM call, no debate. Reads the four analyst reports directly (same
inputs the debate_enabled=False Trader path already reads) and extracts named,
bounded factors into FactorExtraction. This node makes NO decision -- the
deterministic scorer in decision_model.py does that, from these factors alone.
Keeping extraction and scoring as separate steps is the point: the LLM cannot
see or influence the scoring formula or its thresholds.

Deliberately does NOT use agent_utils.invoke_structured_or_freetext -- that
helper's free-text fallback returns a rendered string, not a parsed object,
which would leave decision_model.py with nothing to score. A structured-output
failure here falls back to a neutral FactorExtraction (no catalyst, zero
direction/confidence) instead, which score_factors() maps to Hold -- a safe
default consistent with the prompt's own guidance to abstain absent evidence,
never to a free-text guess decision_model.py can't parse.
"""

from __future__ import annotations

import logging

from tradingagents.agents.schemas import FactorExtraction
from tradingagents.agents.utils.agent_utils import (
    external_signal_prompt_block,
    get_external_signal_direction_from_state,
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import NO_EXTERNAL_TOOLS, bind_structured

from .decision_model import score_factors

logger = logging.getLogger(__name__)

_NEUTRAL_FACTORS = FactorExtraction(
    dated_catalyst_present=False,
    catalyst_hours_to_resolution=None,
    technical_direction=0.0,
    technical_confidence=0.0,
    sentiment_direction=0.0,
    sentiment_confidence=0.0,
    risk_flags=["factor_extraction_failed"],
)


def create_factor_extractor(llm):
    structured_llm = bind_structured(llm, FactorExtraction, "Factor Extractor")

    def factor_extractor_node(state) -> dict:
        company_name = state["company_of_interest"]
        instrument_context = get_instrument_context_from_state(state)
        # TradingAgents#30: the upstream signal is shown so a sector-wide,
        # same-session catalyst the ticker-scoped news search never surfaced
        # can still be recorded as dated_catalyst_present. Its direction is
        # NOT for the extractor to copy into the direction fields -- the
        # deterministic scorer applies it as a separate signed prior.
        external_block = external_signal_prompt_block(state)
        external_section = (
            f"\n{external_block}\nThe signal above is a dated, same-session event for this instrument's "
            f"sector/basket -- if the reports do not contradict it, count it towards dated_catalyst_present. "
            f"Do NOT fold its direction into technical_direction/sentiment_direction; those must reflect the "
            f"reports only. The scorer applies the signal's direction separately.\n"
            if external_block else ""
        )

        prompt = f"""You are extracting structured factors from analyst reports for {company_name}. {instrument_context}

Your ONLY job is to read the four reports below and extract the factors in the schema -- you are not making a trading decision, a separate deterministic step does that from your factors alone. Score honestly: if the technical picture is genuinely two-sided, technical_confidence should be low, not padded to look decisive. If no analyst identified a catalyst that resolves within this decision's own short holding window (same session or next open), dated_catalyst_present must be false even if a longer-horizon story exists.
{external_section}
**Market Report:**
{state.get('market_report', 'N/A')}

**Sentiment Report:**
{state.get('sentiment_report', 'N/A')}

**News Report:**
{state.get('news_report', 'N/A')}

**Fundamentals Report:**
{state.get('fundamentals_report', 'N/A')}

{NO_EXTERNAL_TOOLS}""" + get_language_instruction()

        factors = None
        if structured_llm is not None:
            try:
                factors = structured_llm.invoke(prompt)
            except Exception as exc:
                logger.warning(
                    "Factor Extractor: structured-output invocation failed (%s); "
                    "using neutral factors (-> Hold)", exc,
                )
        if factors is None:
            factors = _NEUTRAL_FACTORS

        investment_plan = score_factors(
            factors, company_name=company_name,
            external_direction=get_external_signal_direction_from_state(state) or None,
        )

        return {
            "extracted_factors": factors,
            "investment_plan": investment_plan,
        }

    return factor_extractor_node
