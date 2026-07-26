"""Persist immutable reports, deterministic trust, and formal advice versions."""

from __future__ import annotations

import re
from typing import Any

from tradingagents.persistence import Repository
from tradingagents.trust import assess_result_evidence
from tradingagents.usage.budget import summarize_usage

REPORT_SECTIONS = (
    ("market_report", "Market Analysis"),
    ("sentiment_report", "Sentiment Analysis"),
    ("news_report", "News Analysis"),
    ("fundamentals_report", "Fund Analysis"),
    ("investment_plan", "Research Decision"),
    ("trader_investment_plan", "Trading Plan"),
    ("final_trade_decision", "Final Decision"),
)


def deterministic_action(result: dict[str, Any]) -> str:
    decision = str(result.get("final_trade_decision") or "").lower()
    china_fund = isinstance(result.get("china_fund_snapshot"), dict)
    if re.search(r"\b(sell|underweight)\b", decision):
        return "redeem_partial" if china_fund else "sell"
    if re.search(r"\b(buy|overweight|accumulate)\b", decision):
        return "subscribe" if china_fund else "buy"
    return "hold"


def render_markdown(result: dict[str, Any], trust: dict[str, Any] | None = None) -> str:
    title = result.get("company_of_interest", "Unknown instrument")
    lines = [
        f"# Trading Analysis Report: {title}", "",
        f"- Asset type: {result.get('asset_type', 'unknown')}",
        f"- Analysis date: {result.get('trade_date', 'unknown')}",
        f"- Benchmark: {result.get('benchmark_symbol', 'unknown')}",
        f"- Generated: {result.get('generated_at', 'unknown')}",
    ]
    for key, heading in REPORT_SECTIONS:
        if result.get(key):
            lines.extend(["", f"## {heading}", "", str(result[key])])
    if trust:
        lines.extend([
            "", "## Data Quality", "",
            f"- Trust level: {trust['level']}",
            f"- Recommendation eligibility: {'executable' if trust['executable'] else 'observation-only'}",
            f"- Reason codes: {', '.join(trust['reason_codes']) or 'none'}",
        ])
        for warning in trust.get("warnings", []):
            lines.append(f"- Warning: {warning}")
        lines.extend(["", "### Evidence", "", "| Field | Freshness | Effective at | Source |", "| --- | --- | --- | --- |"])
        for item in trust.get("evidence", []):
            lines.append(f"| {item['name']} | {item['freshness_status']} | {item.get('effective_at') or 'unknown'} | {item['source_reference']} |")
    return "\n".join(lines)


class ArtifactService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def persist_analysis(self, job: Any, result: dict[str, Any]) -> dict[str, str]:
        observation, assessment = assess_result_evidence(result, job_id=job.id)
        self.repository.add_observation(observation)
        self.repository.add_trust(assessment)
        trust_data = {
            "id": assessment.id,
            "level": assessment.level,
            "executable": assessment.executable,
            "reason_codes": list(assessment.reason_codes),
            "warnings": list(assessment.warnings),
            "evidence": [item.__dict__ for item in assessment.evidence],
        }
        result["data_quality"] = trust_data
        markdown = render_markdown(result, trust_data)
        report = self.repository.create_report(job.id, result, markdown)
        usage = summarize_usage(self.repository.list_usage(job_id=job.id))
        action = deterministic_action(result)
        advice = self.repository.create_advice(
            report.id,
            action=action,
            confidence="medium" if assessment.level == "trusted" else "low",
            reason="Formal recommendation derived from the persisted report and trust gate.",
            eligibility="executable" if assessment.executable else "observation_only",
            trust_assessment_id=assessment.id,
            data_snapshot={"observation_id": observation.id, "raw_hash": observation.raw_hash},
            model_config={
                "provider": job.request.get("llm_provider"),
                "quick_model": job.request.get("quick_model"),
                "deep_model": job.request.get("deep_model"),
            },
            usage=usage,
        )
        return {"report_id": report.id, "advice_id": advice.id}
