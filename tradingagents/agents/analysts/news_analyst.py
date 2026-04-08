from datetime import datetime, timedelta
import logging

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    prefetch_tools_parallel,
)
from tradingagents.agents.utils.news_data_tools import get_global_news, get_news
from tradingagents.agents.utils.context_filtering import filter_scanner_context_for_ticker
from tradingagents.agents.utils.llm_guard import invoke_with_timeout
from tradingagents.agents.utils.output_validation import (
    log_validation_result,
    render_structured_news_payload,
    validate_structured_news_payload,
)
from tradingagents.memory.news_evidence import NewsEvidenceStore
from tradingagents.default_config import DEFAULT_CONFIG

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


def _build_timeout_structured_payload(
    *,
    ticker: str,
    records: list,
    fallback_date: str,
    max_claims: int = 3,
) -> dict:
    ticker_upper = str(ticker or "").upper()
    claims: list[dict] = []
    summary_rows: list[dict] = []

    for record in records[:max_claims]:
        published_at = str(getattr(record, "published_at", "") or fallback_date).strip()
        source = str(getattr(record, "source", "") or "Unknown").strip()
        evidence_id = str(getattr(record, "evidence_id", "")).strip()
        title = str(getattr(record, "title", "")).strip()
        if not title or not evidence_id:
            continue

        claim_text = f"{ticker_upper}: {title} ({published_at})."
        claims.append(
            {
                "claim": claim_text,
                "source": source,
                "published_at": published_at,
                "evidence_id": evidence_id,
            }
        )
        summary_rows.append(
            {
                "date": published_at,
                "event": title[:80],
                "metric": "Article",
                "value": "Captured",
                "source": source,
                "evidence_id": evidence_id,
            }
        )

    return {
        "ticker": ticker_upper,
        "report_title": f"{ticker_upper} News Analysis",
        "claims": claims,
        "summary_table": summary_rows,
    }


def _build_compact_news_context(
    *,
    records: list,
    max_items: int = 8,
    max_summary_chars: int = 220,
) -> str:
    """Build a deterministic, prompt-light context from persisted evidence records."""
    lines = [
        "## Deterministic News Context",
        "",
        "Use only the evidence rows below when generating claims.",
        "",
    ]
    if not records:
        lines.append("_No evidence records available._")
        return "\n".join(lines)

    for record in records[:max_items]:
        evidence_id = str(getattr(record, "evidence_id", "")).strip()
        source = str(getattr(record, "source", "")).strip() or "Unknown"
        published_at = str(getattr(record, "published_at", "")).strip() or "N/A"
        section_label = str(getattr(record, "section_label", "")).strip() or "News"
        title = str(getattr(record, "title", "")).strip()
        summary = str(getattr(record, "summary", "")).strip()
        if len(summary) > max_summary_chars:
            summary = summary[:max_summary_chars].rstrip() + "..."
        lines.append(
            f"- [Evidence ID: {evidence_id}] "
            f"Source: {source} | Published: {published_at} | Section: {section_label}"
        )
        if title:
            lines.append(f"  Title: {title}")
        if summary:
            lines.append(f"  Summary: {summary}")
        lines.append("")
    return "\n".join(lines).strip()


def create_news_analyst(llm, evidence_store: NewsEvidenceStore | None = None):
    store = evidence_store or NewsEvidenceStore()

    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        run_id = str(state["run_id"])
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
        evidence_records = store.ingest_prefetched_sections(
            run_id=run_id,
            ticker=ticker,
            trade_date=current_date,
            prefetched=prefetched,
        )
        compact_news_context = _build_compact_news_context(records=evidence_records)
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
            "- Output ONLY valid JSON. Do not wrap the JSON in markdown fences.\n"
            "- Cite exact values in standard format inside claim text: $X.XX, +Y.Y% YoY. No superlatives (\"massive\", \"huge\", \"significant\"). Every claim must reference a specific number, date, or source.\n"
            "- Prioritize material news with quantifiable impact over speculative commentary.\n"
            "- Attribute each claim to a specific source and date.\n\n"
            "Return a JSON object with this schema:\n"
            "{\n"
            f'  "ticker": "{ticker}",\n'
            f'  "report_title": "{ticker} News Analysis",\n'
            '  "claims": [\n'
            "    {\n"
            '      "claim": "One sentence grounded in the provided context that includes the ticker symbol.",\n'
            '      "source": "Exact source name from the provided evidence records or Finviz Smart Money Scanner",\n'
            '      "published_at": "YYYY-MM-DD",\n'
            '      "evidence_id": "art_...",\n'
            '      "scan_date": "YYYY-MM-DD"\n'
            "    }\n"
            "  ],\n"
            '  "summary_table": [\n'
            "    {\n"
            '      "date": "YYYY-MM-DD",\n'
            '      "event": "Short event label",\n'
            '      "metric": "Metric name",\n'
            '      "value": "Exact value string",\n'
            '      "source": "Exact source name",\n'
            '      "evidence_id": "art_..."\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Use `scan_date` only for Finviz Smart Money Scanner claims. Use `published_at` and `evidence_id` for article-based claims.\n\n"
            "When citing scanner-derived claims, use this exact format: "
            f"{scanner_citation_hint}\n"
            "When a matching persisted article is available in the Deterministic News Context section, "
            "prefer to append its stable evidence handle in the form "
            "`[Evidence ID: ...]` so the claim can be traced back later.\n"
            "Only cite publications or data sources that appear in the provided news feeds or the exact scanner citation above.\n"
            "Internal prompt labels and section headers are NOT sources. Never cite labels such as "
            "\"Macro Regime Classification\", \"Scanner Context\", \"Pre-loaded Context\", or "
            "\"Economic Calendar\" as publications.\n"
            "Do not invent source names. Do not describe Finviz scanner output as SEC or Form 4 evidence unless SEC filing data is explicitly present in the provided news context.\n\n"
            "If the evidence window is sparse, return only the claims you can verify from the provided context. "
            "Do not invent filler claims to satisfy a target count.\n\n"
            "Start with the company-specific news block and anchor the report on developments "
            f"that are directly material to {ticker}. Use the global macroeconomic block only "
            "as secondary context. If the company feed includes peer, ETF, or sector articles "
            "that mention the ticker only in passing, treat them as lower-priority spillover "
            "signals rather than core evidence.\n\n"
            "Synthesize the pre-loaded news feeds into a comprehensive report covering the "
            "current state of the world as it is relevant to trading and macroeconomics. "
            "Cross-reference company-specific developments with the broader macro backdrop. "
            "Provide specific, actionable insights with supporting evidence to help traders "
            "make informed decisions. Populate the `summary_table` with the most decision-relevant "
            "rows from the same validated evidence."
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
                    "{compact_news_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(scanner_context=scanner_context)
        prompt = prompt.partial(compact_news_context=compact_news_context)

        # No tools remain — use direct invocation (no bind_tools, no tool loop)
        chain = prompt | llm

        timeout_seconds = min(
            float(DEFAULT_CONFIG.get("mid_think_llm_timeout") or DEFAULT_CONFIG.get("llm_timeout") or 120.0),
            float(DEFAULT_CONFIG.get("mid_think_llm_timeout_cap") or 60.0),
        )
        first_result, invoke_error = invoke_with_timeout(
            llm=chain,
            prompt_or_messages=state["messages"],
            timeout_seconds=timeout_seconds,
        )
        if invoke_error is not None:
            if isinstance(invoke_error, TimeoutError):
                timeout_payload = _build_timeout_structured_payload(
                    ticker=ticker,
                    records=evidence_records,
                    fallback_date=current_date,
                )
                timeout_report = render_structured_news_payload(timeout_payload, ticker)
                return {
                    "messages": [AIMessage(content=timeout_report)],
                    "news_report": timeout_report,
                    "news_report_structured": timeout_payload,
                }
            raise invoke_error
        raw_output = first_result.content or ""
        structured_validation = validate_structured_news_payload(
            raw_output,
            ticker,
            min_claims=1,
        )
        report = (
            render_structured_news_payload(structured_validation.payload, ticker)
            if structured_validation.is_valid and structured_validation.payload is not None
            else raw_output
        )

        log_validation_result(
            agent_name="news_analyst_attempt_1",
            ticker=ticker,
            is_valid=structured_validation.is_valid,
            reason=structured_validation.reason,
            output_preview=raw_output[:500] if raw_output else "",
        )

        result = first_result
        structured_payload = (
            structured_validation.payload if structured_validation.is_valid else None
        )
        if not structured_validation.is_valid:
            logger.warning(
                "News analyst output validation failed for %s on attempt 1 (%s): %s",
                ticker,
                structured_validation.code,
                structured_validation.reason,
            )
            retry_instruction = HumanMessage(
                content=(
                    "Validation failed for your prior draft.\n"
                    f"Failure code: {structured_validation.code}\n"
                    f"Failure reason: {structured_validation.reason}\n"
                    "The same full scanner context, pre-loaded news feeds, and persisted evidence records "
                    "remain available on this retry.\n"
                    "Rewrite the report from scratch using only the provided context and return valid JSON only. "
                    "Only cite publications or data sources present in the provided feeds. "
                    "Do not cite internal prompt labels or section headers like "
                    "\"Macro Regime Classification\", \"Scanner Context\", or "
                    "\"Pre-loaded Context\" as sources. "
                    f"If you cite scanner-derived claims, you must use {scanner_citation_hint} exactly. "
                    "Every article-based claim must include exact `source`, `published_at`, and `evidence_id` fields."
                )
            )
            result, invoke_error = invoke_with_timeout(
                llm=chain,
                prompt_or_messages=[*state["messages"], retry_instruction],
                timeout_seconds=timeout_seconds,
            )
            if invoke_error is not None:
                if isinstance(invoke_error, TimeoutError):
                    timeout_payload = _build_timeout_structured_payload(
                        ticker=ticker,
                        records=evidence_records,
                        fallback_date=current_date,
                    )
                    report = render_structured_news_payload(timeout_payload, ticker)
                    return {
                        "messages": [AIMessage(content=report)],
                        "news_report": report,
                        "news_report_structured": timeout_payload,
                    }
                raise invoke_error
            raw_output = result.content or ""
            structured_validation = validate_structured_news_payload(
                raw_output,
                ticker,
                min_claims=1,
            )
            report = (
                render_structured_news_payload(structured_validation.payload, ticker)
                if structured_validation.is_valid and structured_validation.payload is not None
                else raw_output
            )
            log_validation_result(
                agent_name="news_analyst_attempt_2",
                ticker=ticker,
                is_valid=structured_validation.is_valid,
                reason=structured_validation.reason,
                output_preview=raw_output[:500] if raw_output else "",
            )

            if not structured_validation.is_valid:
                logger.error(
                    "News analyst output validation failed for %s on attempt 2 (%s): %s",
                    ticker,
                    structured_validation.code,
                    structured_validation.reason,
                )
                report = (
                    "[CRITICAL ABORT] Reason: News analysis failed source-validation twice "
                    f"for {ticker} ({structured_validation.code}) - {structured_validation.reason}"
                )
                structured_payload = None
            else:
                structured_payload = structured_validation.payload
        else:
            structured_payload = structured_validation.payload

        return {
            "messages": [result],
            "news_report": report,
            "news_report_structured": structured_payload or {},
        }

    return news_analyst_node
