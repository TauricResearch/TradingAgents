from collections.abc import Callable
from typing import Any

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.anonymization import anonymize_ticker
from tradingagents.agents.utils.historical_context import (
    find_latest_execution_failures,
    format_execution_failure_block,
)
from tradingagents.agents.utils.llm_guard import invoke_with_timeout, resolve_timeout, truncate_text
from tradingagents.agents.utils.output_validation import (
    build_investment_plan_structured,
    output_contains_scratchpad,
)
from tradingagents.agents.utils.summary_context import (
    build_research_packet,
    get_investment_debate_summary,
)
from tradingagents.default_config import DEFAULT_CONFIG


def create_research_manager(llm: Any, memory: Any) -> Callable[[AgentState], dict[str, Any]]:
    def research_manager_node(state: AgentState, /) -> dict[str, Any]:

        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        history = state["investment_debate_state"].get("history", "")
        debate_summary = get_investment_debate_summary(state)
        macro_regime_report = state.get("macro_regime_report", "")
        research_packet = build_research_packet(state)

        investment_debate_state = state["investment_debate_state"]

        macro_section = f"\n\nMacro Regime:\n{macro_regime_report}" if macro_regime_report else ""
        curr_situation = f"{research_packet}{macro_section}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)
        past_memory_str = "\n\n".join(rec["recommendation"] for rec in past_memories)

        macro_context = (
            f"\n\nCurrent Macro Regime:\n{macro_regime_report}\nWeight your decision in line with this macro environment — a risk-off regime raises the bar for BUY decisions, while risk-on supports them.\n"
            if macro_regime_report
            else ""
        )
        violations = state.get("consistency_violations") or []
        if violations:
            correction_block = (
                "\n\n## CORRECTION REQUIRED\n"
                "Your previous response contained numeric claims that contradict the "
                "fundamentals report. Address each violation below by either correcting "
                "the number to match the fundamentals report or removing the claim:\n"
                + "\n".join(f"- {v.get('claim', '')}: {v.get('reason', '')}" for v in violations)
            )
        else:
            correction_block = ""

        # Anonymize data variables to prevent training-data bias
        anon_research_packet = anonymize_ticker(
            truncate_text(research_packet, max_chars=5000), ticker
        )
        anon_debate_summary = anonymize_ticker(
            truncate_text(debate_summary, max_chars=1800), ticker
        )
        anon_history = anonymize_ticker(truncate_text(history, max_chars=1500), ticker)
        anon_past_memory_str = anonymize_ticker(
            truncate_text(past_memory_str, max_chars=1600), ticker
        )

        # Execution failure injection — uses DEFAULT_CONFIG portfolio_id because
        # the trading graph state does not carry portfolio_id (it's per-ticker).
        # NOTE: failure data may not match the active portfolio if run outside
        # the default portfolio context (e.g. from the portfolio graph that
        # carries its own portfolio_id in state). See caching plan Option A.
        execution_failures = find_latest_execution_failures(
            portfolio_id=str(DEFAULT_CONFIG.get("default_portfolio_id") or "main_portfolio"),
            as_of_date=str(state.get("trade_date") or ""),
        )
        execution_failure_block = format_execution_failure_block(execution_failures)
        # Anonymize ticker references in failure block to prevent training-data bias
        if execution_failure_block:
            execution_failure_block = anonymize_ticker(execution_failure_block, ticker)

        _failure_suffix = f"\n\n{execution_failure_block}" if execution_failure_block else ""

        prompt = f"""As the Research Manager and debate facilitator, critically evaluate this round of debate and make a definitive decision: Buy, Sell, or Hold.
{macro_context}

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis. NO conversational filler or narrative.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY. No superlatives.
- Weight HIGH-confidence claims from the debate over MED/LOW claims.
- Do NOT default to Hold simply because both sides have valid points. Commit to a stance grounded in the debate's strongest evidence.
- **GROUND TRUTH**: The compressed research packet contains a "Scanner Context (Phase 1)" section with verified commodity prices, FX rates, and calendar dates. Use ONLY those values when citing oil, gold, bitcoin prices, FX levels, or event dates. Do NOT invent, estimate, or contradict these ground-truth figures. If an analyst report contradicts the Scanner Context numbers, flag the discrepancy and use the Scanner Context value.
{correction_block}

## MANDATORY CONFLICT RESOLUTION

Before writing your final recommendation, you MUST complete this checklist:

1. List every bearish or risk point from the Fundamentals Analyst report (FCF, debt, margins, working capital, peer rank).
2. For each point, provide a data-backed counter-argument explaining why it is NOT a deal-breaker given current conditions.
3. If you cannot provide a data-backed counter-argument for ANY fundamental deterioration flag (e.g. negative working capital, FCF decline >50%, operating margin <0%), you MUST downgrade your rating by at least one level.
4. Scanner Context signals ("Golden Overlap", "Smart Money Drift", institutional accumulation) are SUPPORTING evidence — they cannot override actual financial deterioration without a specific catalyst that explains why the deterioration is temporary.
5. Your final rating must be consistent with the weakest un-rebutted fundamental risk you identified.

YOUR TASK:
1. **Strongest Bull Evidence**: List the top 3 data-backed bull arguments with confidence tags.
2. **Strongest Bear Evidence**: List the top 3 data-backed bear arguments with confidence tags.
3. **Recommendation**: Buy, Sell, or Hold — decisive, grounded in the highest-confidence evidence.
4. **Rationale**: Why the winning evidence outweighs the opposing side.
5. **Strategic Actions**: Concrete implementation steps for the trader.

Take into account past mistakes on similar situations:
\"{anon_past_memory_str}\"

{instrument_context}

Compressed research packet:
{anon_research_packet}

Rolling debate summary:
{anon_debate_summary}

Here is the debate:
Debate History:
{anon_history}{_failure_suffix}"""
        timeout_seconds = resolve_timeout("deep")
        response, invoke_error = invoke_with_timeout(
            llm,
            prompt,
            timeout_seconds=timeout_seconds,
            max_tokens=DEFAULT_CONFIG.get("deep_think_llm_max_tokens"),
        )

        is_timeout = False
        if invoke_error is not None:
            if isinstance(invoke_error, TimeoutError):
                is_timeout = True
            else:
                err_type = type(invoke_error).__name__
                raise RuntimeError(
                    f"Node execution failed: {err_type} - {str(invoke_error)}"
                ) from invoke_error

        # If it was a timeout or if the content is empty/garbage, apply the deterministic fallback.
        output_content = ""
        if response:
            output_content = response.content.replace("TICKER_A", ticker)

        if (
            is_timeout
            or not str(output_content).strip()
            or output_contains_scratchpad(output_content)
        ):
            failure_class = (
                "timeout"
                if is_timeout
                else ("empty" if not str(output_content).strip() else "scratchpad")
            )
            raise RuntimeError(
                f"Research Manager node failed: {failure_class} — no valid output after exhausting retries"
            )

        structured = build_investment_plan_structured(
            ticker=ticker,
            as_of_date=state.get("trade_date", ""),
            investment_plan=output_content,
            is_timeout_fallback=False,
            llm=llm,
        )

        new_investment_debate_state = {
            "judge_decision": output_content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": output_content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": output_content,
            "investment_plan_structured": structured,
        }

    return research_manager_node
