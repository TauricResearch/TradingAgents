from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.critical_abort import report_has_critical_abort
from tradingagents.agents.utils.output_validation import (
    build_news_report_structured,
    render_structured_news_payload,
    sanitize_structured_news_payload,
    validate_news_analysis_detailed,
    validate_structured_news_payload,
)
from tradingagents.memory.news_evidence import NewsEvidenceStore

logger = logging.getLogger(__name__)


def _has_scanner_structured_claims(payload: object) -> bool:
    """Return True when a structured payload contains scanner-backed claims."""
    if not isinstance(payload, dict):
        return False
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return False
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        source = str(claim.get("source") or "").strip()
        scan_date = str(claim.get("scan_date") or "").strip()
        if source == "Finviz Smart Money Scanner" and scan_date:
            return True
    return False
def create_news_fact_checker(
    llm: Any, evidence_store: NewsEvidenceStore | None = None
) -> Callable[[AgentState], dict[str, Any]]:
    store = evidence_store or NewsEvidenceStore()

    def news_fact_checker_node(state: AgentState, /) -> dict[str, Any]:

        ticker = str(state.get("company_of_interest") or "").upper()
        trade_date = str(state.get("trade_date") or "")
        run_id = str(state["run_id"])
        report = str(state.get("news_report") or "").strip()
        structured_payload = state.get("news_report_structured")
        
        # Fetch persisted evidence records
        records = store.fetch_records(run_id=run_id, ticker=ticker, trade_date=trade_date)
        allowed_source_names = {record.source for record in records if record.source}
        allowed_evidence_ids = {record.evidence_id for record in records if record.evidence_id}
        records_by_id = {record.evidence_id: record for record in records if record.evidence_id}
        
        # Branch: No persisted evidence records and no critical abort
        # (Evidence acquisition succeeded but no news found, or all prefetch failed)
        if (
            not records
            and not report_has_critical_abort(report)
            and not _has_scanner_structured_claims(structured_payload)
        ):
            return {
                "news_report": f"{ticker} News Analysis\n\n- No validated news was available for this run.",
                "news_report_structured": build_news_report_structured(
                    ticker=ticker,
                    as_of_date=trade_date,
                    payload={},
                    status="empty",
                    abort_reason="",
                ),
                "sender": "news_fact_checker",
            }
        
        # Branch: Existing [CRITICAL ABORT] report (analyst timeout or prefetch failure)
        if report_has_critical_abort(report):
            abort_reason = report.split("[CRITICAL ABORT]", 1)[1].strip(" :\n\t") if "[CRITICAL ABORT]" in report else "Critical abort"
            return {
                "news_report": report,  # Preserve upstream critical abort markdown
                "news_report_structured": build_news_report_structured(
                    ticker=ticker,
                    as_of_date=trade_date,
                    payload={},
                    status="aborted",
                    abort_reason=abort_reason,
                ),
                "sender": "news_fact_checker",
            }
        
        # Branch: Blank report with missing payload
        if not report and (not isinstance(structured_payload, dict) or not structured_payload):
            return {
                "news_report": f"{ticker} News Analysis\n\n- No validated structured news claims are available for this run.",
                "news_report_structured": build_news_report_structured(
                    ticker=ticker,
                    as_of_date=trade_date,
                    payload={},
                    status="missing_structured_payload",
                    abort_reason="No structured payload was supplied by the analyst node",
                ),
                "sender": "news_fact_checker",
            }
        
        # Branch: Blank report with structured payload present
        # Continue to validation/sanitization flow - if claims validate, render from canonical claims
        
        # Branch: Missing payload (not a dict or empty dict)
        if not isinstance(structured_payload, dict) or not structured_payload:
            return {
                "news_report": f"{ticker} News Analysis\n\n- No validated structured news claims are available for this run.",
                "news_report_structured": build_news_report_structured(
                    ticker=ticker,
                    as_of_date=trade_date,
                    payload={},
                    status="missing_structured_payload",
                    abort_reason="No structured payload was supplied by the analyst node",
                ),
                "sender": "news_fact_checker",
            }
        
        # Validate structured payload schema
        structured_validation = validate_structured_news_payload(
            json.dumps(structured_payload),
            ticker,
            min_claims=1,
        )
        
        # Branch: Invalid payload (validation fails)
        # DO NOT emit new [CRITICAL ABORT] - return deterministic non-evidence message
        if not structured_validation.is_valid or structured_validation.payload is None:
            abort_reason = f"{structured_validation.code}: {structured_validation.reason}"
            return {
                "news_report": f"{ticker} News Analysis\n\n- No validated structured news claims are available for this run.",
                "news_report_structured": build_news_report_structured(
                    ticker=ticker,
                    as_of_date=trade_date,
                    payload={},
                    status="invalid_structured_payload",
                    abort_reason=abort_reason,
                ),
                "sender": "news_fact_checker",
            }
        
        # Sanitize payload against persisted evidence
        sanitized_payload, removed_claims = sanitize_structured_news_payload(
            structured_validation.payload,
            ticker=ticker,
            allowed_source_names=allowed_source_names,
            allowed_evidence_ids=allowed_evidence_ids,
            evidence_records_by_id=records_by_id,
            min_claims=1,
        )
        
        claim_count = len(sanitized_payload.get("claims") or [])
        
        # Branch: Zero claims after sanitization with removed claims
        # All submitted claims were rejected
        if claim_count == 0 and removed_claims:
            return {
                "news_report": f"{ticker} News Analysis\n\n- No validated structured news claims are available for this run.",
                "news_report_structured": build_news_report_structured(
                    ticker=ticker,
                    as_of_date=trade_date,
                    payload=sanitized_payload,
                    status="invalid_structured_payload",
                    abort_reason="All structured claims were removed during fact-checking",
                    removed_claims=removed_claims,
                ),
                "sender": "news_fact_checker",
            }
        
        # Branch: Zero claims after sanitization without removed claims
        # No validated claims were produced (empty but valid)
        if claim_count == 0:
            return {
                "news_report": f"{ticker} News Analysis\n\n- No validated news was available for this run.",
                "news_report_structured": build_news_report_structured(
                    ticker=ticker,
                    as_of_date=trade_date,
                    payload=sanitized_payload,
                    status="empty",
                    abort_reason="",
                    removed_claims=removed_claims,
                ),
                "sender": "news_fact_checker",
            }
        
        # Render markdown from canonical sanitized claims
        rendered_report = render_structured_news_payload(sanitized_payload, ticker)
        
        # Validate rendered report (secondary quality check)
        validation = validate_news_analysis_detailed(
            rendered_report,
            ticker,
            allowed_source_names=allowed_source_names,
            allowed_evidence_ids=allowed_evidence_ids,
            enforce_provenance=True,
            min_ticker_mentions=max(1, min(3, claim_count)),
        )
        
        # Branch: Rendered report fails validation
        # DO NOT critical abort - sanitized claims already passed evidence-based provenance checks
        # Log warning and return completed contract
        if not validation.is_valid:
            logger.warning(
                "News fact-checker: rendered report failed secondary validation "
                f"for {ticker} ({validation.code}): {validation.reason}. "
                "Returning completed contract with sanitized claims."
            )
        
        # Branch: Happy path - 1+ verified claims remaining
        return {
            "news_report": rendered_report,
            "news_report_structured": build_news_report_structured(
                ticker=ticker,
                as_of_date=trade_date,
                payload=sanitized_payload,
                status="completed",
                abort_reason="",
                removed_claims=removed_claims,
            ),
            "sender": "news_fact_checker",
        }

    return news_fact_checker_node
