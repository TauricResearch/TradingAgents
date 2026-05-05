from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from tradingagents.agents.utils.rating import parse_rating


_TICKER_RE = re.compile(r"\b[A-Z]{2,5}(?:\.[A-Z]{1,4})?\b")
_SOURCE_RE = re.compile(r"https?://|\b(source|according to|reported by|yahoo finance|alpha vantage)\b", re.IGNORECASE)
_SOURCE_ID_RE = re.compile(r"\b(?:SRC-[A-Z]+-\d+|RAW-TOOL-\d+)\b")
_RECONCILIATION_RE = re.compile(r"\b(scorecard|reconcile|despite|offset|override|because)\b", re.IGNORECASE)

_COMMON_NON_TICKERS = {
    "AI",
    "API",
    "AT",
    "ATR",
    "BUY",
    "CEO",
    "CFO",
    "CSV",
    "DB",
    "EMA",
    "ETF",
    "FINAL",
    "GDP",
    "HOLD",
    "JSON",
    "LLM",
    "MACD",
    "NASDAQ",
    "NYSE",
    "OVERWEIGHT",
    "PDF",
    "PE",
    "P/E",
    "RSI",
    "SRC",
    "RAW",
    "TOOL",
    "SMA",
    "US",
    "USD",
    "VWAP",
    "MARKET",
    "NEWS",
    "RISK",
    "SOCIAL",
    "SENTIMENT",
    "SELL",
    "UNDERWEIGHT",
    "FUNDAMENTALS",
}

_ISSUER_ALIASES = {
    "AAPL": {"apple"},
    "AMZN": {"amazon"},
    "GOOGL": {"alphabet", "google"},
    "JPM": {"jpmorgan", "jp morgan", "jpmorgan chase"},
    "MSFT": {"microsoft"},
    "NVDA": {"nvidia"},
    "TSLA": {"tesla"},
}

_KNOWN_OTHER_ISSUERS = {
    "alphabet": "GOOGL",
    "apple": "AAPL",
    "amazon": "AMZN",
    "avalyn": "AVLN",
    "google": "GOOGL",
    "jpmorgan": "JPM",
    "marvell": "MRVL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "tesla": "TSLA",
}


@dataclass(frozen=True)
class QualityFinding:
    code: str
    severity: str
    message: str
    evidence: str | None = None


@dataclass(frozen=True)
class QualityAssessment:
    status: str
    findings: list[QualityFinding] = field(default_factory=list)
    source_summary: dict[str, Any] = field(default_factory=dict)
    recommendation_audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "findings": [finding.__dict__ for finding in self.findings],
            "source_summary": self.source_summary,
            "recommendation_audit": self.recommendation_audit,
        }


def _canonical_symbol(ticker: str) -> str:
    return ticker.split(".", 1)[0].upper()


def _extract_tickers(text: str) -> set[str]:
    return {
        match.group(0)
        for match in _TICKER_RE.finditer(text or "")
        if match.group(0) not in _COMMON_NON_TICKERS
    }


def _report_present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _extract_research_rating(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"recommendation\s*\**\s*[:\-]\s*\**\s*(\w+)", text, re.IGNORECASE)
    if match:
        return parse_rating(f"Rating: {match.group(1)}", default="")
    rating = parse_rating(text, default="")
    return rating or None


def _extract_trader_action(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"(?:action|final transaction proposal)\s*\**\s*[:\-]\s*\**\s*(buy|hold|sell)", text, re.IGNORECASE)
    if match:
        return match.group(1).capitalize()
    for action in ("buy", "hold", "sell"):
        if re.search(rf"\b{action}\b", text, re.IGNORECASE):
            return action.capitalize()
    return None


def _rating_direction(rating: str | None) -> str | None:
    if rating in ("Buy", "Overweight"):
        return "bullish"
    if rating == "Hold":
        return "neutral"
    if rating in ("Underweight", "Sell"):
        return "bearish"
    return None


def _action_direction(action: str | None) -> str | None:
    if action == "Buy":
        return "bullish"
    if action == "Hold":
        return "neutral"
    if action == "Sell":
        return "bearish"
    return None


def _source_objects(state: dict[str, Any]) -> list[dict[str, Any]]:
    value = state.get("source_objects")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _source_registry(state: dict[str, Any]) -> dict[str, Any]:
    value = state.get("source_registry")
    return value if isinstance(value, dict) else {}


def _claim_graph(state: dict[str, Any]) -> dict[str, Any]:
    value = state.get("claim_graph")
    return value if isinstance(value, dict) else {}


def _target_profile(state: dict[str, Any]) -> dict[str, Any]:
    value = state.get("target_profile")
    return value if isinstance(value, dict) else {}


def _valid_source_ids(sources: list[dict[str, Any]]) -> set[str]:
    return {
        str(item["source_id"])
        for item in sources
        if isinstance(item.get("source_id"), str) and item["source_id"].strip()
    }


def _raw_tool_outputs(state: dict[str, Any]) -> list[dict[str, Any]]:
    value = state.get("raw_tool_outputs")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _scorecard_reconciliation(
    *,
    final_rating: str | None,
    final_direction: str | None,
    scorecard: dict[str, Any],
    decision: str,
) -> dict[str, Any]:
    scorecard_rating = scorecard.get("suggested_rating")
    scorecard_direction = scorecard.get("suggested_direction")
    if not final_direction or not scorecard_direction:
        status = "unscored"
    elif final_direction == scorecard_direction:
        status = "aligned"
    else:
        status = "divergent"
    explicit_reconciliation = bool(_RECONCILIATION_RE.search(decision))
    requires_reconciliation = status == "divergent"
    return {
        "status": status,
        "final_rating": final_rating or None,
        "final_direction": final_direction,
        "scorecard_rating": scorecard_rating,
        "scorecard_direction": scorecard_direction,
        "explicit_reconciliation": explicit_reconciliation,
        "requires_reconciliation": requires_reconciliation,
        "reconciled": not requires_reconciliation or explicit_reconciliation,
    }


def _build_recommendation_audit(
    *,
    ticker: str,
    decision: str,
    state: dict[str, Any],
    report_presence: dict[str, bool],
) -> dict[str, Any]:
    final_rating = parse_rating(decision, default="")
    research_rating = _extract_research_rating(state.get("investment_plan"))
    trader_action = _extract_trader_action(state.get("trader_investment_plan") or state.get("trader_investment_decision"))
    final_direction = _rating_direction(final_rating)
    research_direction = _rating_direction(research_rating)
    trader_direction = _action_direction(trader_action)
    scorecard = state.get("recommendation_scorecard") if isinstance(state.get("recommendation_scorecard"), dict) else {}
    scorecard_reconciliation = _scorecard_reconciliation(
        final_rating=final_rating,
        final_direction=final_direction,
        scorecard=scorecard,
        decision=decision,
    )
    claim_graph = _claim_graph(state)
    claim_objects = claim_graph.get("claim_objects") if isinstance(claim_graph.get("claim_objects"), list) else []
    claim_objects = [claim for claim in claim_objects if isinstance(claim, dict)]
    target_profile = _target_profile(state)
    target_profile_text = " ".join(str(value) for value in target_profile.values() if value is not None).strip().lower()
    decision_text = decision.lower()
    target_profile_status = "not_present"
    target_profile_addressed = False
    if target_profile:
        target_profile_status = "not_addressed"
        target_profile_addressed = any(
            phrase in decision_text
            for phrase in (
                "target profile",
                "investor profile",
                "risk appetite",
                "benchmark",
                "horizon",
                target_profile_text,
            )
            if phrase
        )
        if target_profile_addressed:
            target_profile_status = "addressed"

    alignment_inputs = [value for value in (research_direction, trader_direction, final_direction) if value]
    aligned = len(set(alignment_inputs)) <= 1 if alignment_inputs else False
    report_count = sum(1 for present in report_presence.values() if present)
    cited_source_ids = sorted(set(_SOURCE_ID_RE.findall(decision)))
    explicit_source_reference = bool(_SOURCE_RE.search(decision) or cited_source_ids)
    source_registry = state.get("source_registry") if isinstance(state.get("source_registry"), dict) else {}
    claim_graph = state.get("claim_graph") if isinstance(state.get("claim_graph"), dict) else {}

    return {
        "requested_ticker": ticker,
        "final_rating": final_rating or None,
        "research_manager_rating": research_rating,
        "trader_action": trader_action,
        "directions": {
            "research_manager": research_direction,
            "trader": trader_direction,
            "portfolio_manager": final_direction,
        },
        "alignment_status": "aligned" if aligned else "divergent",
        "intermediate_report_count": report_count,
        "explicit_source_reference": explicit_source_reference,
        "available_source_ids": sorted(_valid_source_ids(_source_objects(state))),
        "cited_source_ids": cited_source_ids,
        "scorecard": scorecard,
        "scorecard_suggested_rating": scorecard.get("suggested_rating"),
        "scorecard_suggested_direction": scorecard.get("suggested_direction"),
        "scorecard_alignment_status": scorecard_reconciliation["status"],
        "rating_vs_scorecard": scorecard_reconciliation["status"],
        "scorecard_reconciliation": scorecard_reconciliation,
        "claim_graph_summary": {
            "claim_count": len(claim_objects),
            "claim_source_ids": sorted({
                source_id
                for claim in claim_objects
                for source_id in (claim.get("source_ids") or [])
                if isinstance(source_id, str) and source_id.strip()
            }),
            "claim_backed_factor_count": int(scorecard.get("claim_backed_factor_count") or 0),
        },
        "target_profile": target_profile,
        "target_profile_status": target_profile_status,
        "methodology": (
            "LLM synthesis over analyst reports and debates; deterministic audit checks "
            "rating/action alignment, report availability, source IDs, claim graph coverage, "
            "claim-backed scorecard evidence, target profile alignment, and ticker/entity scope."
        ),
        "source_registry": source_registry,
        "claim_graph": {
            "claim_count": len(claim_graph.get("claim_objects") or []),
            "claim_ids": claim_graph.get("claim_ids", []),
            "claim_source_ids": claim_graph.get("claim_source_ids", []),
        },
    }


def assess_shadow_run_quality(
    *,
    ticker: str,
    final_trade_decision: str | None,
    final_state: dict[str, Any] | None = None,
) -> QualityAssessment:
    """Deterministically flag obvious defects in model-generated analysis.

    This does not grade investment merit. It catches workflow hazards that are
    cheap to detect before handing output to Flint: ticker contamination,
    unrelated issuer mentions, missing reports, and missing explicit sources.
    """
    symbol = _canonical_symbol(ticker)
    decision = final_trade_decision or ""
    state = final_state or {}
    findings: list[QualityFinding] = []

    mentioned = _extract_tickers(decision)
    unrelated_tickers = sorted(t for t in mentioned if _canonical_symbol(t) != symbol)
    if unrelated_tickers:
        findings.append(
            QualityFinding(
                code="unrelated_ticker_mention",
                severity="error",
                message=f"Decision mentions ticker(s) outside requested instrument {ticker}.",
                evidence=", ".join(unrelated_tickers),
            )
        )

    allowed_aliases = _ISSUER_ALIASES.get(symbol, {symbol.lower()})
    other_issuers = []
    lower_decision = decision.lower()
    for issuer, issuer_symbol in _KNOWN_OTHER_ISSUERS.items():
        if issuer_symbol == symbol or issuer in allowed_aliases:
            continue
        if re.search(rf"\b{re.escape(issuer)}\b", lower_decision):
            other_issuers.append(f"{issuer} ({issuer_symbol})")
    if other_issuers:
        findings.append(
            QualityFinding(
                code="unrelated_entity_mention",
                severity="error",
                message=f"Decision mentions issuer(s) unrelated to requested instrument {ticker}.",
                evidence=", ".join(sorted(other_issuers)),
            )
        )

    report_keys = ("market_report", "news_report", "sentiment_report", "fundamentals_report")
    report_presence = {key: _report_present(state.get(key)) for key in report_keys}
    sources = _source_objects(state)
    source_registry = _source_registry(state)
    claim_graph = _claim_graph(state)
    raw_tool_outputs = _raw_tool_outputs(state)
    raw_tool_ids = {
        str(item["source_id"])
        for item in raw_tool_outputs
        if isinstance(item.get("source_id"), str) and item["source_id"].strip()
    }
    valid_source_ids = _valid_source_ids(sources) | raw_tool_ids
    cited_source_ids = set(_SOURCE_ID_RE.findall(decision))
    invalid_source_ids = cited_source_ids - valid_source_ids
    raw_tool_names = {
        str(item.get("tool_name", "unknown"))
        for item in raw_tool_outputs
    }
    recommendation_audit = _build_recommendation_audit(
        ticker=ticker,
        decision=decision,
        state=state,
        report_presence=report_presence,
    )
    pre_synthesis_scope_audit = (
        state.get("pre_synthesis_scope_audit")
        if isinstance(state.get("pre_synthesis_scope_audit"), dict)
        else {}
    )
    selected_reports_present = any(report_presence.values())
    if not selected_reports_present:
        findings.append(
            QualityFinding(
                code="missing_intermediate_reports",
                severity="error",
                message="No intermediate analyst reports were available for quality inspection.",
            )
        )

    if valid_source_ids and not cited_source_ids:
        findings.append(
            QualityFinding(
                code="missing_source_object_citation",
                severity="error",
                message="Structured source objects were produced, but the final decision cites none of their source IDs.",
                evidence=", ".join(sorted(valid_source_ids)),
            )
        )

    if invalid_source_ids:
        findings.append(
            QualityFinding(
                code="invalid_source_object_citation",
                severity="error",
                message="Final decision cites source IDs that were not produced for this run.",
                evidence=", ".join(sorted(invalid_source_ids)),
            )
        )

    if raw_tool_ids and not (cited_source_ids & raw_tool_ids):
        findings.append(
            QualityFinding(
                code="missing_raw_tool_citation",
                severity="error",
                message="Raw tool output sources were captured, but the final decision cites none of their RAW-TOOL source IDs.",
                evidence=", ".join(sorted(raw_tool_ids)),
            )
        )

    if not (_SOURCE_RE.search(decision) or cited_source_ids):
        findings.append(
            QualityFinding(
                code="no_explicit_source_reference",
                severity="warning",
                message="Final decision lacks explicit source references or URLs.",
            )
        )

    if recommendation_audit["alignment_status"] == "divergent":
        findings.append(
            QualityFinding(
                code="recommendation_chain_divergent",
                severity="warning",
                message="Research Manager, Trader, and Portfolio Manager recommendation directions do not align.",
                evidence=str(recommendation_audit["directions"]),
            )
        )

    for finding in pre_synthesis_scope_audit.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        if finding.get("severity") == "error":
            findings.append(
                QualityFinding(
                    code="pre_synthesis_scope_contamination",
                    severity="error",
                    message=str(finding.get("message") or "Pre-synthesis scope audit found out-of-scope evidence."),
                    evidence=str(finding.get("evidence") or ""),
                )
            )

    if state.get("raw_tool_provenance_expected") and not raw_tool_outputs:
        findings.append(
            QualityFinding(
                code="missing_raw_tool_provenance",
                severity="warning",
                message="Raw tool provenance capture was expected for this service run, but no tool outputs were recorded.",
            )
        )

    scorecard_reconciliation = recommendation_audit.get("scorecard_reconciliation") or {}
    if scorecard_reconciliation.get("requires_reconciliation") and not scorecard_reconciliation.get("reconciled"):
        findings.append(
            QualityFinding(
                code="scorecard_reconciliation_missing",
                severity="error",
                message="Final rating diverges from deterministic scorecard direction without an explicit reconciliation.",
                evidence=(
                    f"final={scorecard_reconciliation.get('final_direction')} "
                    f"scorecard={scorecard_reconciliation.get('scorecard_direction')}"
                ),
            )
        )

    claim_graph_summary = recommendation_audit.get("claim_graph_summary") or {}
    has_claim_graph = isinstance(_claim_graph(state), dict) and bool(_claim_graph(state))
    claim_count = int(claim_graph_summary.get("claim_count") or 0)
    claim_source_ids = claim_graph_summary.get("claim_source_ids") or []
    claim_backed_factor_count = int(claim_graph_summary.get("claim_backed_factor_count") or 0)
    if has_claim_graph and (sources or raw_tool_outputs) and claim_count == 0:
        findings.append(
            QualityFinding(
                code="missing_claim_graph_evidence",
                severity="error",
                message="Structured source objects were produced, but no claim graph evidence was extracted for synthesis.",
            )
        )
    if has_claim_graph and claim_count and not claim_source_ids:
        findings.append(
            QualityFinding(
                code="unlinked_claim_evidence",
                severity="error",
                message="Claim graph was produced, but no claim in the graph is linked back to a source ID.",
            )
        )
    if has_claim_graph and claim_count and claim_backed_factor_count == 0:
        findings.append(
            QualityFinding(
                code="scorecard_claim_backing_missing",
                severity="error",
                message="Deterministic scorecard was produced without any claim-backed factors.",
                evidence="claim_graph present but scorecard factors lack claim ids",
            )
        )

    target_profile = recommendation_audit.get("target_profile") if isinstance(recommendation_audit.get("target_profile"), dict) else {}
    target_profile_status = recommendation_audit.get("target_profile_status")
    if target_profile and target_profile_status == "not_addressed":
        findings.append(
            QualityFinding(
                code="target_profile_not_addressed",
                severity="warning",
                message="Target profile was supplied, but final decision does not explicitly address investor horizon, benchmark, or risk appetite.",
                evidence=", ".join(sorted(target_profile.keys())) or "target_profile",
            )
        )

    status = "failed" if any(f.severity == "error" for f in findings) else "warning" if findings else "passed"
    return QualityAssessment(
        status=status,
        findings=findings,
        source_summary={
            "requested_ticker": ticker,
            "mentioned_tickers": sorted(mentioned),
            "report_presence": report_presence,
            "source_object_count": len(sources),
            "source_registry_count": len(source_registry.get("source_objects") or []),
            "claim_count": len(claim_graph.get("claim_objects") or []),
            "claim_source_ids": recommendation_audit.get("claim_graph_summary", {}).get("claim_source_ids", []),
            "claim_backed_factor_count": recommendation_audit.get("claim_graph_summary", {}).get("claim_backed_factor_count", 0),
            "valid_source_ids": sorted(valid_source_ids),
            "cited_source_ids": sorted(cited_source_ids),
            "invalid_source_ids": sorted(invalid_source_ids),
            "raw_tool_output_count": len(raw_tool_outputs),
            "raw_tool_output_ids": sorted(raw_tool_ids),
            "raw_tool_names": sorted(raw_tool_names),
            "raw_tool_provenance": state.get("raw_tool_provenance") if isinstance(state.get("raw_tool_provenance"), dict) else {},
            "pre_synthesis_scope_audit": pre_synthesis_scope_audit,
            "target_profile": target_profile,
            "target_profile_status": target_profile_status,
        },
        recommendation_audit=recommendation_audit,
    )
