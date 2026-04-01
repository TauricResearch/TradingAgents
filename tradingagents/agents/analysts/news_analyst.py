from datetime import datetime, timedelta
import logging

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    format_prefetched_context,
    prefetch_tools_parallel,
)
from tradingagents.agents.utils.news_data_tools import get_global_news, get_news
from tradingagents.agents.utils.context_filtering import filter_scanner_context_for_ticker
from tradingagents.agents.utils.output_validation import (
    validate_news_analysis,
    format_validation_warning,
    log_validation_result,
)

logger = logging.getLogger(__name__)


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        
        # Apply ticker-specific filtering to reduce scanner context from ~10K to ~3-4K tokens
        scanner_context_raw = state.get("scanner_context_packet", "")
        scanner_context = filter_scanner_context_for_ticker(
            scanner_context_raw, ticker
        ) if scanner_context_raw else ""

        # ── Pre-fetch company-specific and global news in parallel ────────────
        trade_date = datetime.strptime(current_date, "%Y-%m-%d")
        start_date = (trade_date - timedelta(days=7)).strftime("%Y-%m-%d")

        prefetched = prefetch_tools_parallel(
            [
                {
                    "tool": get_news,
                    "args": {
                        "ticker": ticker,
                        "start_date": start_date,
                        "end_date": current_date,
                    },
                    "label": "Company-Specific News (Last 7 Days)",
                },
                {
                    "tool": get_global_news,
                    "args": {
                        "curr_date": current_date,
                        "look_back_days": 7,
                        "limit": 5,
                    },
                    "label": "Global Macroeconomic News (Last 7 Days)",
                },
            ]
        )
        prefetched_context = format_prefetched_context(prefetched)

        macro_regime_report = state.get("macro_regime_report", "")
        macro_regime_section = (
            "\n## Current Macro Regime\n"
            f"{macro_regime_report}\n\n"
            "In risk-off regimes, prioritize regulatory and macroeconomic news over earnings "
            "surprises. In risk-on regimes, prioritize growth catalysts and expansion news.\n"
            if macro_regime_report
            else ""
        )

        system_message = (
            "You are a news researcher tasked with analyzing recent news and trends over "
            "the past week.\n\n"
            "## Pre-loaded Data\n\n"
            "Both company-specific news and global macroeconomic news for the past 7 days "
            "have already been fetched and are provided in the **Pre-loaded Context** section "
            "below. Do NOT call `get_news` or `get_global_news` — the data is already available.\n\n"
            f"{macro_regime_section}"
            "## Your Task\n\n"
            "0. **STRICT GROUND TRUTH**: Treat all values in the **Scanner Context** section "
            "(commodity prices, FX rates, and calendar dates) as absolute ground-truth. "
            "Use the provided **Economic Calendar** to contextulize news events — "
            "do NOT hallucinate dates for FOMC, CPI, or other macro releases.\n\n"
            "STRICT CONSTRAINTS:\n"
            "- Output ONLY bulleted quantitative analysis with a summary table.\n"
            "- Cite exact values in standard format: $X.XX, +Y.Y% YoY. No superlatives (\"massive\", \"huge\", \"significant\"). Every claim must reference a specific number, date, or source.\n"
            "- Prioritize material news with quantifiable impact over speculative commentary.\n"
            "- Attribute each claim to a specific source and date.\n\n"
            f"**CRITICAL OUTPUT REQUIREMENTS**:\n"
            f"Your response MUST satisfy ALL of these validation criteria:\n"
            f"1. Mention the ticker symbol \"{ticker}\" at least 5 times\n"
            f"2. Include at least 3 specific quotes or facts directly from the provided news articles\n"
            f"3. Reference specific dates (YYYY-MM-DD format) and sources for all major claims\n"
            f"4. Include concrete numbers ($X.XX, Y.Y%, specific quantities)\n"
            f"5. If you find yourself writing generic portfolio strategy advice (diversification, risk tolerance, rebalancing), STOP - that is WRONG\n\n"
            f"**SELF-VALIDATION CHECK** (before finalizing your response):\n"
            f"- Does it mention {ticker} at least 5 times? ✓\n"
            f"- Does it quote specific articles with dates? ✓\n"
            f"- Does it include concrete numbers and percentages? ✓\n"
            f"- Does it avoid generic investment advice? ✓\n\n"
            f"If NO to any of the above, your response FAILED validation. Start over and focus strictly on the {ticker} news articles.\n\n"
            "Start with the company-specific news block and anchor the report on developments "
            f"that are directly material to {ticker}. Use the global macroeconomic block only "
            "as secondary context. If the company feed includes peer, ETF, or sector articles "
            "that mention the ticker only in passing, treat them as lower-priority spillover "
            "signals rather than core evidence.\n\n"
            "Synthesize the pre-loaded news feeds into a comprehensive report covering the "
            "current state of the world as it is relevant to trading and macroeconomics. "
            "Cross-reference company-specific developments with the broader macro backdrop. "
            "Provide specific, actionable insights with supporting evidence to help traders "
            "make informed decisions. "
            "Make sure to append a Markdown table at the end of the report to organise key "
            "points, making it easy to read."
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}\n\n"
                    "## Scanner Context\n\n{scanner_context}\n\n"
                    "## Pre-loaded Context\n\n{prefetched_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        
        # Validate output quality
        is_valid, reason = validate_news_analysis(report, ticker)
        
        # Log validation result for monitoring
        log_validation_result(
            agent_name="news_analyst",
            ticker=ticker,
            is_valid=is_valid,
            reason=reason,
            output_preview=report[:500] if report else ""
        )
        
        # If validation fails, prepend warning to output (visible to user/downstream agents)
        if not is_valid:
            logger.warning(
                f"News analyst output validation failed for {ticker}: {reason}"
            )
            report = format_validation_warning(report, ticker, reason)

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(scanner_context=scanner_context)
        prompt = prompt.partial(prefetched_context=prefetched_context)

        # No tools remain — use direct invocation (no bind_tools, no tool loop)
        chain = prompt | llm

        result = chain.invoke(state["messages"])

        report = result.content or ""

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
