"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back to a free-text invocation and the existing heuristic rating parser.
"""

from __future__ import annotations

import logging

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)

logger = logging.getLogger(__name__)


def create_portfolio_manager(llm):
    # Wrap once at agent construction; if the provider does not support
    # structured output we keep ``structured_llm`` as None and use the
    # free-text fallback for every call.
    try:
        structured_llm = llm.with_structured_output(PortfolioDecision)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "Portfolio Manager: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            exc,
        )
        structured_llm = None

    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        final_trade_decision = _invoke_pm(structured_llm, llm, prompt)

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
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
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node


def _invoke_pm(structured_llm, plain_llm, prompt: str) -> str:
    """Run the PM call and return the markdown-rendered decision.

    Tries the structured-output path first; if it fails for any reason
    (provider does not support it, model returns malformed JSON, network
    glitch on the structured endpoint), falls back to the plain free-text
    invocation so the pipeline still produces a result.
    """
    if structured_llm is not None:
        try:
            decision = structured_llm.invoke(prompt)
            return render_pm_decision(decision)
        except Exception as exc:
            logger.warning(
                "Portfolio Manager: structured-output invocation failed (%s); "
                "retrying once as free text",
                exc,
            )

    response = plain_llm.invoke(prompt)
    return response.content
