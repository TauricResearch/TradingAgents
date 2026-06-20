"""Portfolio Manager: synthesises the risk-analyst debate into the final decision.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation.
"""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_position_context_from_state,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = get_instrument_context_from_state(state)
        position_context = get_position_context_from_state(state)

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

        # Re-check mode: when an original_thesis is present, the PM is
        # judging whether prior reasoning still holds rather than producing
        # a disconnected fresh analysis. Build the comparison block and the
        # explicit intact/weakening/broken instruction.
        original_thesis = state.get("original_thesis", "")
        if original_thesis:
            recheck_block = (
                "\n---\n\n"
                "**This is a RE-CHECK run, not an initial analysis.**\n\n"
                f"{original_thesis}\n\n"
                "Your task is to evaluate whether the original reasoning above "
                "still holds, given today's fresh analyst debate. Open the "
                "executive_summary with an explicit classification — one of:\n"
                "- **Thesis intact** — the original case is still valid; nothing material has changed.\n"
                "- **Thesis weakening** — parts of the original case are no longer well supported; flag specifically what.\n"
                "- **Thesis broken** — a load-bearing pillar of the original case has failed; the original reasoning no longer stands.\n\n"
                "Then state the resulting action against the user's current position "
                "(e.g. 'thesis intact, sit tight on the existing £800', "
                "'thesis weakening, trim to £400 while you re-evaluate', "
                "'thesis broken, exit'). Cite specifically what has changed since the original run.\n"
            )
        else:
            recheck_block = ""

        prompt = f"""As the Portfolio Manager for a retail investor's satellite portfolio, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

{position_context}

---

**Investor context** (applies to every decision):
- This is a retail satellite portfolio. Most positions are around £100, occasionally up to ~£2,000 for high-conviction ideas. Speak in £ amounts, never percentages of portfolio or AUM.
- Long-term orientation: the default hold is months to years, not days. The investor is not trading on technicals or short-term catalysts.
- The investor maintains a soft ~3-month minimum hold as a personal discipline against reacting to noise. Factor it when framing exit or reduction timing, but it is not a hard rule and does not override the thesis — say what you actually think, and let the investor decide.
- The investor always makes the final call. Be honest, not hedged: "the thesis is weak, don't initiate" is more useful than a hedged Hold that doesn't steer.
- The investor is new to finance. Do not assume any baseline of investing vocabulary — even commonly cited "basics" like PE, EPS, market cap, dividend yield, support/resistance, beta, and bull/bear should NOT be assumed to be understood. Any finance, accounting, or trading term beyond day-to-day plain English (the basics above plus more advanced terms like free cash flow conversion, operating leverage, PEG, DCF, EV/EBITDA, gross-margin compression, insider ratio, short interest, guidance, re-rating, catalyst, moat, drawdown, etc.) must be glossed briefly in plain English the first time it appears. Keep the analytical substance; just make every term land. Frame it like writing for an intelligent friend who doesn't work in finance — the investor should finish reading knowing more than when they started.

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

---

**Time Horizon** — populate honestly. Either a date-style estimate ("near-term catalyst, resolves within a quarter") or a condition-based answer ("no fixed horizon — hold while gross margins keep expanding; reassess if that reverses") is a complete answer. A condition-based answer is not a fallback; it is the right answer when the thesis is structural. Do not fabricate a date when the thesis does not warrant one.

---

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}
{recheck_block}
---

The executive_summary must open by anchoring in the user's actual position status (above). If they hold the name, frame as add / maintain / trim / exit. If they hold nothing, frame as initiate or do-not-initiate. Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )

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
