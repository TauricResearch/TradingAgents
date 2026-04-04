import functools

from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.anonymization import anonymize_ticker
from tradingagents.agents.utils.llm_guard import invoke_with_timeout, truncate_text
from tradingagents.agents.utils.output_validation import (
    build_trader_plan_fallback,
    build_trader_plan_structured,
    output_contains_scratchpad,
)
from tradingagents.default_config import DEFAULT_CONFIG
from langchain_core.messages import AIMessage


def create_trader(llm, memory):
    def trader_node(state, name):
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        scanner_context = state.get("scanner_context_packet", "")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        # Anonymize data variables to prevent training-data bias
        anon_investment_plan = anonymize_ticker(
            truncate_text(investment_plan, max_chars=3000), ticker
        )
        anon_past_memory_str = anonymize_ticker(
            truncate_text(past_memory_str, max_chars=1600), ticker
        )

        scanner_section = ""
        if scanner_context:
            scanner_section = (
                "\n\n## Scanner Ground-Truth Data\n"
                "The following commodity prices, FX rates, and calendar dates are verified "
                "live data. Use ONLY these values for catalyst dates, commodity references, "
                "and FX levels. Do NOT estimate or hallucinate any dates or prices.\n\n"
                f"{scanner_context}"
            )

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for the stock. {instrument_context} This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {anon_investment_plan}\n\nLeverage these insights to make an informed and strategic decision.{scanner_section}",
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a trading execution specialist converting the Research Manager's recommendation into a precise transaction proposal.

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis. NO conversational filler.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY. No superlatives.
- Every proposal must include entry price, stop-loss (5-15% below entry), and take-profit (10-30% above entry).
- For the Catalyst Timeline, use ONLY dates from the Scanner Ground-Truth Data section. Do NOT estimate or invent earnings dates, FOMC dates, CPI dates, or any other event dates.

YOUR TASK:
1. **Research Manager's Verdict**: Restate the recommendation and top evidence.
2. **Entry Setup**: Specific entry price or range with technical justification.
3. **Risk Parameters**: Stop-loss level, take-profit target, position size rationale.
4. **Catalyst Timeline**: Key upcoming dates (earnings, ex-div, macro events) from the ground-truth calendar data ONLY.
5. **FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL****

Apply lessons from past decisions:
{anon_past_memory_str}""",
            },
            context,
        ]

        timeout_seconds = min(
            float(DEFAULT_CONFIG.get("mid_think_llm_timeout") or DEFAULT_CONFIG.get("llm_timeout") or 120.0),
            float(DEFAULT_CONFIG.get("mid_think_llm_timeout_cap") or 60.0),
        )
        result, invoke_error = invoke_with_timeout(
            llm,
            messages,
            timeout_seconds=timeout_seconds,
            max_tokens=900,
        )
        if invoke_error is not None:
            if isinstance(invoke_error, TimeoutError):
                result = AIMessage(
                    content=(
                        "- Research Manager's Verdict: HOLD via timeout fallback.\n"
                        "- Entry Setup: No new entry until the trading plan can be regenerated.\n"
                        "- Risk Parameters: No new order; preserve existing position controls only.\n"
                        "- Catalyst Timeline: Use only scanner ground-truth dates already present in upstream context.\n"
                        "- FINAL TRANSACTION PROPOSAL: **HOLD**"
                    )
                )
            else:
                raise invoke_error

        # De-anonymize: replace TICKER_A back with the real ticker.
        output_content = result.content.replace("TICKER_A", ticker)
        is_timeout = isinstance(invoke_error, TimeoutError) if invoke_error else False
        if output_contains_scratchpad(output_content):
            output_content = build_trader_plan_fallback(state)

        structured = build_trader_plan_structured(
            ticker=ticker,
            as_of_date=state.get("trade_date", ""),
            trader_plan=output_content,
            is_timeout_fallback=is_timeout,
        )

        return {
            "messages": [result],
            "trader_investment_plan": output_content,
            "trader_plan_structured": structured,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
