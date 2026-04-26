from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.critical_abort import has_abort, raise_abort
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

        def _abort_result(
            *,
            reason: str,
            detail: str,
            payload: dict[str, Any] | None = None,
            removed_claims: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            structured = build_news_report_structured(
                ticker=ticker,
                as_of_date=trade_date,
                payload=payload or {},
                status="aborted",
                abort_reason=detail,
                removed_claims=removed_claims or [],
            )
            if removed_claims:
                structured["removed_claims"] = [
                    {
                        **removed_claim,
                        "source": (
                            removed_claim.get("claim", {}).get("source", "")
                            if isinstance(removed_claim.get("claim"), dict)
                            else ""
                        ),
                        "evidence_id": (
                            removed_claim.get("claim", {}).get("evidence_id", "")
                            if isinstance(removed_claim.get("claim"), dict)
                            else ""
                        ),
                    }
                    for removed_claim in removed_claims
                ]
            return {
                "news_report": (
                    f"{ticker} News Analysis\n\n"
                    "- No validated structured news claims are available for this run."
                ),
                "news_report_structured": structured,
                "sender": "news_fact_checker",
                **raise_abort(
                    source="news_fact_checker",
                    reason=reason,
                    detail=detail,
                    recoverable=True,
                ),
            }

        if has_abort(state):
            abort_signal = state.get("abort_signal") or {}
            abort_reason = ": ".join(
                part
                for part in [
                    str(abort_signal.get("reason") or "").strip(),
                    str(abort_signal.get("detail") or "").strip(),
                ]
                if part
            )
            return {
                "news_report": report,
                "news_report_structured": build_news_report_structured(
                    ticker=ticker,
                    as_of_date=trade_date,
                    payload={},
                    status="aborted",
                    abort_reason=abort_reason or "Structured abort signal raised",
                ),
                "sender": "news_fact_checker",
            }

        # Fetch persisted evidence records
        records = store.fetch_records(run_id=run_id, ticker=ticker, trade_date=trade_date)
        allowed_source_names = {record.source for record in records if record.source}
        allowed_evidence_ids = {record.evidence_id for record in records if record.evidence_id}
        records_by_id = {record.evidence_id: record for record in records if record.evidence_id}

        # Branch: No persisted evidence records
        # (Evidence acquisition succeeded but no news found.)
        if not records and not _has_scanner_structured_claims(structured_payload):
            return _abort_result(
                reason="news_evidence_missing",
                detail=(
                    f"No NewsEvidenceStore records found for run_id={run_id!r}, "
                    f"ticker={ticker!r}, trade_date={trade_date!r}"
                ),
            )

        # Branch: Blank report with missing payload
        if not report and (not isinstance(structured_payload, dict) or not structured_payload):
            return _abort_result(
                reason="news_schema_invalid",
                detail="No structured payload was supplied by the analyst node",
            )

        # Branch: Blank report with structured payload present
        # Continue to validation/sanitization flow - if claims validate, render from canonical claims

        # Branch: Missing payload (not a dict or empty dict)
        if not isinstance(structured_payload, dict) or not structured_payload:
            return _abort_result(
                reason="news_schema_invalid",
                detail="No structured payload was supplied by the analyst node",
            )

        # Validate structured payload schema
        structured_validation = validate_structured_news_payload(
            json.dumps(structured_payload),
            ticker,
            min_claims=1,
        )

        # Branch: Invalid payload (validation fails)
        # Return deterministic non-evidence message; routing uses abort_signal only.
        if not structured_validation.is_valid or structured_validation.payload is None:
            abort_reason = f"{structured_validation.code}: {structured_validation.reason}"
            return _abort_result(reason="news_schema_invalid", detail=abort_reason)

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

        # Branch: Any submitted claim rejected.
        # ADR 027 requires every decision-effecting news claim to be grounded.
        if removed_claims:
            detail = (
                "All structured claims were removed during fact-checking"
                if claim_count == 0
                else "One or more structured claims were removed during fact-checking"
            )
            return _abort_result(
                reason="news_evidence_missing",
                detail=detail,
                payload=sanitized_payload,
                removed_claims=removed_claims,
            )

        # Branch: Zero claims after sanitization without removed claims
        # No validated claims were produced (empty but valid)
        if claim_count == 0:
            return _abort_result(
                reason="news_evidence_missing",
                detail="No validated structured news claims remain after fact-checking",
                payload=sanitized_payload,
                removed_claims=removed_claims,
            )

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
