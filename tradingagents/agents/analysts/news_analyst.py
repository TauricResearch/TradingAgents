from datetime import datetime, timedelta
import logging

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    format_prefetched_context,
    prefetch_tools_parallel,
)
from tradingagents.agents.utils.news_data_tools import get_global_news, get_news
from tradingagents.agents.utils.context_filtering import filter_scanner_context_for_ticker
from tradingagents.agents.utils.output_validation import (
    extract_allowed_sources_from_context,
    validate_news_analysis_detailed,
    log_validation_result,
)
from tradingagents.memory.news_evidence import NewsEvidenceStore

logger = logging.getLogger(__name__)


def _extract_scanner_citation_hint(scanner_context: str, fallback_date: str) -> str:
    source_match = None
    date_match = None
    if scanner_context:
        source_match = next(
            (line.split(":", 1)[1].strip() for line in scanner_context.splitlines() if line.startswith("Source:")),
            None,
        )
        date_match = next(
            (line.split(":", 1)[1].strip() for line in scanner_context.splitlines() if line.startswith("Scan Date:")),
            None,
        )

    source_name = source_match or "Finviz Smart Money Scanner"
    scan_date = date_match or fallback_date
    return f"[Source: {source_name} | Scan Date: {scan_date}]"


def create_news_analyst(llm, evidence_store: NewsEvidenceStore | None = None):
    store = evidence_store or NewsEvidenceStore()

    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        run_id = str(state.get("run_id") or f"{ticker.upper()}-{current_date}")
        instrument_context = build_instrument_context(ticker)
        
        # Apply ticker-specific filtering to reduce scanner context from ~10K to ~3-4K tokens
        scanner_context_raw = state.get("scanner_context_packet", "")
        scanner_context = filter_scanner_context_for_ticker(
            scanner_context_raw, ticker
        ) if scanner_context_raw else ""
        scanner_citation_hint = _extract_scanner_citation_hint(
            scanner_context, current_date
        )

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
        evidence_records = store.ingest_prefetched_sections(
            run_id=run_id,
            ticker=ticker,
            trade_date=current_date,
            prefetched=prefetched,
        )
        evidence_context = store.build_prompt_context(evidence_records)
        allowed_source_names = (
            {record.source for record in evidence_records if record.source}
            | extract_allowed_sources_from_context(prefetched_context)
        )

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
            "When citing scanner-derived claims, use this exact format: "
            f"{scanner_citation_hint}\n"
            "When a matching persisted article is available in the Evidence Records section, "
            "prefer to append its stable evidence handle in the form "
            "`[Evidence ID: ...]` so the claim can be traced back later.\n"
            "Only cite publications or data sources that appear in the provided news feeds or the exact scanner citation above.\n"
            "Internal prompt labels and section headers are NOT sources. Never cite labels such as "
            "\"Macro Regime Classification\", \"Scanner Context\", \"Pre-loaded Context\", or "
            "\"Economic Calendar\" as publications.\n"
            "Do not invent source names. Do not describe Finviz scanner output as SEC or Form 4 evidence unless SEC filing data is explicitly present in the provided news context.\n\n"
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
                    "{evidence_context}\n\n"
                    "## Pre-loaded Context\n\n{prefetched_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(scanner_context=scanner_context)
        prompt = prompt.partial(evidence_context=evidence_context)
        prompt = prompt.partial(prefetched_context=prefetched_context)

        # No tools remain — use direct invocation (no bind_tools, no tool loop)
        chain = prompt | llm

        first_result = chain.invoke(state["messages"])
        report = first_result.content or ""

        validation = validate_news_analysis_detailed(
            report,
            ticker,
            allowed_source_names=allowed_source_names,
            allowed_evidence_ids={record.evidence_id for record in evidence_records},
            enforce_provenance=False,
        )
        log_validation_result(
            agent_name="news_analyst_attempt_1",
            ticker=ticker,
            is_valid=validation.is_valid,
            reason=validation.reason,
            output_preview=report[:500] if report else ""
        )

        result = first_result
        if not validation.is_valid:
            logger.warning(
                "News analyst output validation failed for %s on attempt 1 (%s): %s",
                ticker,
                validation.code,
                validation.reason,
            )
            retry_instruction = HumanMessage(
                content=(
                    "Validation failed for your prior draft.\n"
                    f"Failure code: {validation.code}\n"
                    f"Failure reason: {validation.reason}\n"
                    "Rewrite the report from scratch using only the provided context. "
                    "Only cite publications or data sources present in the provided feeds. "
                    "Do not cite internal prompt labels or section headers like "
                    "\"Macro Regime Classification\", \"Scanner Context\", or "
                    "\"Pre-loaded Context\" as sources. "
                    f"If you cite scanner-derived claims, you must use {scanner_citation_hint} exactly."
                )
            )
            result = chain.invoke([*state["messages"], retry_instruction])
            report = result.content or ""
            validation = validate_news_analysis_detailed(
                report,
                ticker,
                allowed_source_names=allowed_source_names,
                allowed_evidence_ids={record.evidence_id for record in evidence_records},
                enforce_provenance=False,
            )
            log_validation_result(
                agent_name="news_analyst_attempt_2",
                ticker=ticker,
                is_valid=validation.is_valid,
                reason=validation.reason,
                output_preview=report[:500] if report else ""
            )

            if not validation.is_valid:
                logger.error(
                    "News analyst output validation failed for %s on attempt 2 (%s): %s",
                    ticker,
                    validation.code,
                    validation.reason,
                )
                report = (
                    "[CRITICAL ABORT] Reason: News analysis failed source-validation twice "
                    f"for {ticker} ({validation.code}) - {validation.reason}"
                )

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
