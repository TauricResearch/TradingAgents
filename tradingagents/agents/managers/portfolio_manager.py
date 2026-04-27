from collections.abc import Callable
from typing import Any

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.critical_abort import has_abort
from tradingagents.agents.utils.llm_guard import invoke_with_timeout, resolve_timeout, truncate_text
from tradingagents.agents.utils.output_validation import build_final_decision_structured
from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_risk_debate_summary,
)
from tradingagents.default_config import DEFAULT_CONFIG


def create_portfolio_manager(llm: Any, memory: Any) -> Callable[[AgentState], dict[str, Any]]:
    def portfolio_manager_node(state: AgentState, /) -> dict[str, Any]:

        instrument_context = build_instrument_context(state["company_of_interest"])

        risk_debate_state = state["risk_debate_state"]
        history = truncate_text(risk_debate_state.get("history", ""), max_chars=3200)
        risk_summary = truncate_text(get_risk_debate_summary(state), max_chars=1800)
        trader_plan = state.get("trader_investment_plan", "")
        macro_regime_report = state.get("macro_regime_report", "")
        research_packet = truncate_text(build_research_packet(state), max_chars=5000)

        is_critical_abort = has_abort(state)

        # Build current situation with all reports
        macro_section = f"\n\nMacro Regime:\n{macro_regime_report}" if macro_regime_report else ""
        curr_situation = f"{research_packet}{macro_section}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = "\n\n".join(rec["recommendation"] for rec in past_memories)

        macro_context = (
            f"\n\nCurrent Macro Regime:\n{macro_regime_report}\nEnsure your risk assessment reflects the macro environment — in risk-off regimes, apply higher standards for position entry and tighter risk controls.\n"
            if macro_regime_report
            else ""
        )

        timeout_seconds = resolve_timeout("deep")

        if is_critical_abort:
            abort_signal = state.get("abort_signal") or {}
            abort_report = ": ".join(
                part
                for part in [
                    str(abort_signal.get("reason") or "").strip(),
                    str(abort_signal.get("detail") or "").strip(),
                ]
                if part
            )
            prompt = f"""As the Portfolio Manager, you have received a critical abort signal from an early analyst. This indicates catastrophic conditions (bankruptcy, SEC delisting, etc.) that require immediate action.

{instrument_context}

---

**CRITICAL ABORT DETECTED**

**Aborting Analyst's Report:**
{abort_report}

**Context:**
- Trader's proposed plan: **{trader_plan}**
- Lessons from past decisions: **{past_memory_str}**
- Compressed research packet: **{research_packet}**

**Required Output Structure:**
1. **Rating**: State one of Buy / Overweight / Hold / Underweight / Sell.
2. **Executive Summary**: A concise action plan covering entry strategy, position sizing, key risk levels, and time horizon.
3. **Investment Thesis**: Detailed reasoning based on the critical abort signal and the aborting analyst's report.

---

**IMPORTANT**: Based on the critical abort signal, you should recommend SELL or AVOID. Do not proceed with any other analysis. The aborting analyst has identified fundamental issues that make this investment unacceptable."""

            response, invoke_error = invoke_with_timeout(
                llm,
                prompt,
                timeout_seconds=timeout_seconds,
                max_tokens=DEFAULT_CONFIG.get("deep_think_llm_max_tokens"),
            )
            if invoke_error is not None:
                err_type = type(invoke_error).__name__
                raise RuntimeError(
                    f"Node execution failed: {err_type} - {str(invoke_error)}"
                ) from invoke_error
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
- Compressed research packet: **{research_packet}**

**Required Output Structure:**
1. **Rating**: State one of Buy / Overweight / Hold / Underweight / Sell.
2. **Executive Summary**: A concise action plan covering entry strategy, position sizing, key risk levels, and time horizon.
3. **Investment Thesis**: Detailed reasoning anchored in the analysts' debate and past reflections.

---

**Risk Analysts Debate History:**
{history}

**Rolling Risk Debate Summary:**
{risk_summary}

---

Be decisive and ground every conclusion in specific evidence from the analysts."""

            response, invoke_error = invoke_with_timeout(
                llm,
                prompt,
                timeout_seconds=timeout_seconds,
                max_tokens=DEFAULT_CONFIG.get("deep_think_llm_max_tokens"),
            )
            if invoke_error is not None:
                err_type = type(invoke_error).__name__
                raise RuntimeError(
                    f"Node execution failed: {err_type} - {str(invoke_error)}"
                ) from invoke_error

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state.get("history", ""),
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "summary": risk_debate_state.get("summary", ""),
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": risk_debate_state.get(
                "current_conservative_response", ""
            ),
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state.get("count", 0),
        }

        final_decision_text = response.content
        if not final_decision_text.strip():
            raise RuntimeError(
                "Portfolio Manager node failed: empty LLM response — no genuine rating was produced"
            )
        structured = build_final_decision_structured(
            ticker=state.get("company_of_interest", ""),
            as_of_date=state.get("trade_date", ""),
            final_decision=final_decision_text,
        )

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_decision_text,
            "final_trade_decision_structured": structured,
        }

    return portfolio_manager_node
