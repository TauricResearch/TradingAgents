from __future__ import annotations

import json

from tradingagents.agents.utils.critical_abort import report_has_critical_abort
from tradingagents.agents.utils.output_validation import (
    render_structured_news_payload,
    sanitize_structured_news_payload,
    validate_news_analysis_detailed,
    validate_structured_news_payload,
)
from tradingagents.memory.news_evidence import NewsEvidenceStore


def create_news_fact_checker(evidence_store: NewsEvidenceStore | None = None):
    store = evidence_store or NewsEvidenceStore()

    def news_fact_checker_node(state) -> dict:
        report = str(state.get("news_report") or "").strip()
        if not report or report_has_critical_abort(report):
            return {"sender": "news_fact_checker"}

        ticker = str(state.get("company_of_interest") or "").upper()
        trade_date = str(state.get("trade_date") or "")
        run_id = str(state["run_id"])

        records = store.fetch_records(run_id=run_id, ticker=ticker, trade_date=trade_date)
        allowed_source_names = {record.source for record in records if record.source}
        allowed_evidence_ids = {record.evidence_id for record in records if record.evidence_id}
        records_by_id = {record.evidence_id: record for record in records if record.evidence_id}

        structured_payload = state.get("news_report_structured")
        if not isinstance(structured_payload, dict) or not structured_payload:
            return {
                "news_report": f"{ticker} News Analysis\n\n- No validated news claims were produced for this run.",
                "news_report_structured": {},
                "sender": "news_fact_checker",
            }

        structured_validation = validate_structured_news_payload(
            json.dumps(structured_payload),
            ticker,
            min_claims=1,
        )
        if not structured_validation.is_valid or structured_validation.payload is None:
            return {
                "news_report": (
                    "[CRITICAL ABORT] Reason: News fact checker rejected structured payload "
                    f"for {ticker} ({structured_validation.code}) - {structured_validation.reason}"
                ),
                "news_report_structured": {},
                "sender": "news_fact_checker",
            }

        sanitized_payload, removed_claims = sanitize_structured_news_payload(
            structured_validation.payload,
            ticker=ticker,
            allowed_source_names=allowed_source_names,
            allowed_evidence_ids=allowed_evidence_ids,
            evidence_records_by_id=records_by_id,
            min_claims=1,
        )
        claim_count = len(sanitized_payload.get("claims") or [])
        if claim_count == 0:
            reason = (
                "all structured claims were removed"
                if removed_claims
                else "no validated claims remained"
            )
            return {
                "news_report": (
                    f"{ticker} News Analysis\n\n"
                    f"- No validated news claims remained after fact-checking ({reason})."
                ),
                "news_report_structured": sanitized_payload,
                "sender": "news_fact_checker",
            }

        rendered_report = render_structured_news_payload(sanitized_payload, ticker)
        validation = validate_news_analysis_detailed(
            rendered_report,
            ticker,
            allowed_source_names=allowed_source_names,
            allowed_evidence_ids=allowed_evidence_ids,
            enforce_provenance=True,
            min_ticker_mentions=max(1, min(3, claim_count)),
        )
        if not validation.is_valid:
            return {
                "news_report": (
                    "[CRITICAL ABORT] Reason: News fact checker rendered invalid structured report "
                    f"for {ticker} ({validation.code}) - {validation.reason}"
                ),
                "news_report_structured": sanitized_payload,
                "sender": "news_fact_checker",
            }

        return {
            "news_report": rendered_report,
            "news_report_structured": sanitized_payload,
            "sender": "news_fact_checker",
        }

    return news_fact_checker_node
