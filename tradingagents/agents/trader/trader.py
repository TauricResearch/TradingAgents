import re
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.anonymization import anonymize_ticker
from tradingagents.agents.utils.historical_context import (
    find_latest_execution_failures,
    find_latest_prior_analysis,
    find_latest_prior_pm_decision,
    format_execution_failure_block,
    format_prior_context_block,
)
from tradingagents.agents.utils.llm_guard import invoke_with_timeout, truncate_text
from tradingagents.agents.utils.output_validation import (
    build_trader_plan_structured,
    output_contains_scratchpad,
)
from tradingagents.agents.utils.structured_output import invoke_structured_or_freetext
from tradingagents.agents.utils.structured_schemas import TraderProposalSchema
from tradingagents.default_config import DEFAULT_CONFIG


def _parse_price_token(raw: str) -> float | None:
    token = str(raw or "").strip().replace("$", "").replace(",", "")
    if not token:
        return None
    try:
        value = float(token)
    except Exception:
        return None
    return value if value > 0 else None


def _extract_current_price_from_state(state: AgentState) -> float | None:
    market_structured = state.get("market_report_structured") or {}
    # Prefer the dedicated current_price field (extracted from "current price of $X" prose)
    # over key_levels[0], which is the 200-day SMA — not the live price.
    current_price_str = market_structured.get("current_price")
    if current_price_str:
        parsed = _parse_price_token(current_price_str)
        if parsed is not None:
            return parsed
    return None


def _extract_entry_price_from_plan(plan: str) -> float | None:
    text = str(plan or "")
    entry_patterns = [
        r"entry\s*(?:price|setup|point)?\s*[:\-]?\s*\$([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"buy\s+[A-Z]{1,10}\s+at\s+\$([0-9][0-9,]*(?:\.[0-9]+)?)",
    ]
    for pattern in entry_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            parsed = _parse_price_token(match.group(1))
            if parsed is not None:
                return parsed
    return None


def create_trader(llm: Any, memory: Any) -> Callable[[AgentState], dict[str, Any]]:
    def trader_node(state: AgentState, /) -> dict[str, Any]:

        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        investment_plan = state["investment_plan"]
        investment_plan_structured = state.get("investment_plan_structured") or {}
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        scanner_context = state.get("scanner_graph_context_text", "")

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for _i, rec in enumerate(past_memories, 1):
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

        prior_analysis = find_latest_prior_analysis(
            ticker=ticker,
            as_of_date=str(state.get("trade_date") or ""),
        )
        prior_pm_decision = find_latest_prior_pm_decision(
            portfolio_id=str(DEFAULT_CONFIG.get("default_portfolio_id") or "main_portfolio"),
            as_of_date=str(state.get("trade_date") or ""),
        )
        prior_context_block = format_prior_context_block(
            ticker=ticker,
            prior_analysis=prior_analysis,
            prior_pm_decision=prior_pm_decision,
            max_chars=1200,
        )
        anon_prior_context = (
            truncate_text(anonymize_ticker(prior_context_block, ticker), max_chars=1200)
            if prior_context_block
            else ""
        )

        execution_failures = find_latest_execution_failures(
            portfolio_id=str(DEFAULT_CONFIG.get("default_portfolio_id") or "main_portfolio"),
            as_of_date=str(state.get("trade_date") or ""),
        )
        execution_failure_block = format_execution_failure_block(execution_failures)
        # Anonymize ticker references in failure block to prevent training-data bias
        if execution_failure_block:
            execution_failure_block = anonymize_ticker(execution_failure_block, ticker)

        scanner_section = ""
        if scanner_context:
            role_guidance = "Use the scanner graph context to preserve catalysts, exposure edges, and risk factors when translating research into a trade plan."
            scanner_section = (
                "\n\n## Scanner Graph Context\n\n"
                f"{role_guidance}\n\n"
                "The following commodity prices, FX rates, and calendar dates are verified "
                "live data. Use ONLY these values for catalyst dates, commodity references, "
                "and FX levels. Do NOT estimate or hallucinate any dates or prices.\n\n"
                f"{scanner_context}"
            )

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for the stock. {instrument_context} This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {anon_investment_plan}\n\nLeverage these insights to make an informed and strategic decision.{scanner_section}",
        }

        _prior_suffix = f"\n\n{anon_prior_context}" if anon_prior_context else ""
        _failure_suffix = f"\n\n{execution_failure_block}" if execution_failure_block else ""
        messages = [
            {
                "role": "system",
                "content": f"""You are a trading execution specialist converting the Research Manager's recommendation into a precise transaction proposal.

STRICT CONSTRAINTS:
- Output ONLY bulleted quantitative analysis. NO conversational filler.
- Cite exact values in standard format: $X.XX, +Y.Y% YoY. No superlatives.
- Every proposal must include entry price, stop-loss (5-15% below entry), and take-profit (10-30% above entry).
- For the Catalyst Timeline, use ONLY dates from the Scanner Ground-Truth Data section. Do NOT estimate or invent earnings dates, FOMC dates, CPI dates, or any other event dates.

## VOLATILITY & STOP-LOSS SANITY CHECK (mandatory on every run)

Before setting stop-loss and position size:
1. REALIZED RANGE CHECK: Compare the current session high/low range against the provided ATR.
   - If (session_high - session_low) > ATR, the ATR is STALE. Do not use it directly.
2. ADJUSTED STOP-LOSS RULE: If realized range > ATR, place stop-loss at LEAST 1.5× the provided ATR below entry OR below the nearest named structural support level — whichever is wider.
3. ANTI-AIR-POCKET RULE: A stop-loss must be anchored to a named structural level (prior day close, 200-day SMA, earnings gap fill, named support from the market report). Never place a stop in a price zone with no structural reference.
4. POSITION SIZE RECONCILIATION: If the wider stop forces your dollar-at-risk above your target, reduce share count to keep total risk constant — do not widen the stop AND keep the same size.

YOUR TASK:
1. **Research Manager's Verdict**: Restate the recommendation and top evidence.
2. **Entry Setup**: Specific entry price or range with technical justification.
3. **Risk Parameters**: Stop-loss level, take-profit target, position size rationale.
4. **Catalyst Timeline**: Key upcoming dates (earnings, ex-div, macro events) from the ground-truth calendar data ONLY.
5. **FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL****

Apply lessons from past decisions:
{anon_past_memory_str}{_prior_suffix}{_failure_suffix}""",
            },
            context,
        ]

        # Guardrail: do not fabricate an executable trader plan if the
        # upstream research-manager decision is missing or non-terminal.
        plan_status = str(investment_plan_structured.get("status") or "").strip().lower()
        if not str(investment_plan or "").strip() or plan_status in {
            "empty",
            "timeout_fallback",
            "extraction_failed",
            "aborted",
        }:
            raise RuntimeError(
                "upstream Research Manager plan was empty or non-completed, so trader cannot derive entry/stop/target safely"
            )

        # --- Structured output path (gated by config) ---
        entry_price = None
        if DEFAULT_CONFIG.get("structured_output_enabled", True):

            def _trader_fallback_extractor(text: str) -> dict[str, Any]:
                """Fallback: use existing post-hoc extraction on free-text."""
                return build_trader_plan_structured(
                    ticker=ticker,
                    as_of_date=state.get("trade_date", ""),
                    trader_plan=text,
                    is_timeout_fallback=False,
                    llm=llm,
                )

            schema_instance, raw_text, fallback_dict = invoke_structured_or_freetext(
                llm=llm,
                schema=TraderProposalSchema,
                messages=messages,
                fallback_extractor=_trader_fallback_extractor,
                agent_name="Trader",
                timeout_tier="mid",
                max_tokens=DEFAULT_CONFIG.get("mid_think_llm_max_tokens"),
            )

            if schema_instance is not None:
                # Structured path succeeded — synthesize output_content from schema.
                # Build the text representation in a clear, step-by-step way to avoid
                # the ternary-in-concatenation ambiguity.
                output_content = f"**FINAL TRANSACTION PROPOSAL: {schema_instance.action}**\n\n"
                if schema_instance.entry_price is not None:
                    output_content += f"**Entry Price**: ${schema_instance.entry_price:.2f}\n"
                if schema_instance.stop_loss is not None:
                    output_content += f"**Stop-Loss**: ${schema_instance.stop_loss:.2f}\n"
                if schema_instance.take_profit is not None:
                    output_content += f"**Take-Profit**: ${schema_instance.take_profit:.2f}\n"
                if schema_instance.position_sizing:
                    output_content += f"**Position Sizing**: {schema_instance.position_sizing}\n"
                output_content += (
                    f"\n**Reasoning**: {schema_instance.reasoning}\n\n"
                    f"**Catalyst Timeline**: {schema_instance.catalyst_timeline}"
                )
                output_content = output_content.replace("TICKER_A", ticker)

                structured = {
                    "action": schema_instance.action,
                    "entry_price": schema_instance.entry_price,
                    "stop_loss": schema_instance.stop_loss,
                    "take_profit": schema_instance.take_profit,
                    "position_sizing": schema_instance.position_sizing,
                    "reasoning": schema_instance.reasoning,
                    "catalyst_timeline": schema_instance.catalyst_timeline,
                    "status": "structured",
                }

                # Apply entry-price drift guardrail on structured output too
                entry_price = schema_instance.entry_price
            else:
                # Fallback path
                output_content = raw_text.replace("TICKER_A", ticker)
                if not str(output_content).strip() or output_contains_scratchpad(output_content):
                    failure_class = "empty" if not str(output_content).strip() else "scratchpad"
                    raise RuntimeError(
                        f"Trader node failed: {failure_class} — no valid output after exhausting retries"
                    )
                structured = fallback_dict if fallback_dict else {}
                entry_price = _extract_entry_price_from_plan(output_content)

        else:
            # --- Legacy free-text path (structured_output_enabled=False) ---
            _cap = float(DEFAULT_CONFIG.get("mid_think_llm_timeout_cap") or 240.0)
            timeout_seconds = min(
                float(
                    DEFAULT_CONFIG.get("mid_think_llm_timeout")
                    or DEFAULT_CONFIG.get("llm_timeout")
                    or _cap
                ),
                _cap,
            )
            result, invoke_error = invoke_with_timeout(
                llm,
                messages,
                timeout_seconds=timeout_seconds,
                max_tokens=DEFAULT_CONFIG.get("mid_think_llm_max_tokens"),
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

            output_content = ""
            if result:
                output_content = result.content.replace("TICKER_A", ticker)

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
                    f"Trader node failed: {failure_class} — no valid output after exhausting retries"
                )

            structured = build_trader_plan_structured(
                ticker=ticker,
                as_of_date=state.get("trade_date", ""),
                trader_plan=output_content,
                is_timeout_fallback=False,
                llm=llm,
            )
            entry_price = _extract_entry_price_from_plan(output_content)

        # Guardrail: reject plans anchored to stale prices.
        current_price = _extract_current_price_from_state(state)
        max_entry_drift = float(DEFAULT_CONFIG.get("trader_entry_price_drift_max_pct") or 0.20)
        if current_price and entry_price:
            drift = abs(entry_price - current_price) / current_price
            if drift > max_entry_drift:
                raise RuntimeError(
                    "Trader entry-price validation failed: "
                    f"entry ${entry_price:.2f} deviates from validated current price ${current_price:.2f} "
                    f"by {drift:.1%} (> {max_entry_drift:.0%} threshold)."
                )

        return {
            "messages": [AIMessage(content=output_content)],
            "trader_investment_plan": output_content,
            "trader_plan_structured": structured,
            "sender": "Trader",
        }

    return trader_node
