from __future__ import annotations

import json
from typing import Any

from backend.models import AgentResult, Analysis, Decision
from backend.schemas import AgentResultOut, AnalysisOut, DecisionOut


def serialize_analysis(analysis: Analysis, include_payload: bool = True) -> AnalysisOut:
    payload = None
    if include_payload and analysis.payload_json:
        try:
            payload = json.loads(analysis.payload_json)
        except json.JSONDecodeError:
            payload = None
    agents = [_agent(row) for row in sorted(analysis.agents, key=lambda a: a.agent_name)]
    decision = None
    if analysis.decision:
        decision = DecisionOut(
            action=analysis.decision.action,
            confidence=analysis.decision.confidence,
            risk_level=analysis.decision.risk_level,
            reason=analysis.decision.reason,
            entry_price=analysis.decision.entry_price,
            stop_loss=analysis.decision.stop_loss,
            price_target=analysis.decision.price_target,
            time_horizon=analysis.decision.time_horizon,
            in_plain_language=(payload or {}).get("in_plain_language"),
        )
    return AnalysisOut(
        analysis_id=analysis.id,
        status=analysis.status,
        symbol=analysis.symbol,
        exchange=analysis.exchange,
        analysis_date=analysis.analysis_date,
        provider=analysis.provider,
        model=analysis.model,
        research_depth=analysis.research_depth,
        selected_analysts=[item for item in analysis.selected_analysts.split(",") if item],
        final_decision=analysis.final_decision,
        confidence=analysis.confidence,
        risk_level=analysis.risk_level,
        error_message=analysis.error_message,
        started_at=analysis.started_at,
        completed_at=analysis.completed_at,
        created_at=analysis.created_at,
        agents=agents,
        decision=decision,
        payload=payload if include_payload else None,
    )


def _agent(row: AgentResult) -> AgentResultOut:
    structured = None
    if row.structured_output:
        try:
            structured = json.loads(row.structured_output)
        except json.JSONDecodeError:
            structured = {"full": row.structured_output}
    return AgentResultOut(
        agent_name=row.agent_name,
        status=row.status,
        summary=row.summary,
        structured_output=structured,
    )
