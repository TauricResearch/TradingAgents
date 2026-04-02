from __future__ import annotations

from tradingagents.agents.utils.critical_abort import report_has_critical_abort
from tradingagents.agents.utils.output_validation import (
    filter_news_report_by_provenance,
    validate_news_analysis_detailed,
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
        run_id = str(state.get("run_id") or f"{ticker}-{trade_date}")

        records = store.fetch_records(run_id=run_id, ticker=ticker, trade_date=trade_date)
        allowed_source_names = {record.source for record in records if record.source}
        allowed_evidence_ids = {record.evidence_id for record in records if record.evidence_id}

        validation = validate_news_analysis_detailed(
            report,
            ticker,
            allowed_source_names=allowed_source_names,
            allowed_evidence_ids=allowed_evidence_ids,
            enforce_provenance=True,
        )
        if validation.is_valid or validation.code not in {"unknown_source", "unknown_evidence_id"}:
            return {"sender": "news_fact_checker"}

        sanitized_report, removed_lines = filter_news_report_by_provenance(
            report,
            allowed_source_names=allowed_source_names,
            allowed_evidence_ids=allowed_evidence_ids,
        )
        if not removed_lines:
            return {"sender": "news_fact_checker"}

        sanitized_validation = validate_news_analysis_detailed(
            sanitized_report,
            ticker,
            allowed_source_names=allowed_source_names,
            allowed_evidence_ids=allowed_evidence_ids,
            enforce_provenance=True,
        )
        if sanitized_validation.is_valid:
            return {
                "news_report": sanitized_report,
                "sender": "news_fact_checker",
            }

        return {
            "news_report": (
                "[CRITICAL ABORT] Reason: News fact checker removed unsupported sourced claims "
                f"for {ticker} ({validation.code}); remaining content failed validation - "
                f"{sanitized_validation.reason}"
            ),
            "sender": "news_fact_checker",
        }

    return news_fact_checker_node
