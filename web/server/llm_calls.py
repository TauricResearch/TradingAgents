"""Persistence functions for LlmCall records."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from sqlmodel import select, desc

from web.server.db import get_session, LlmCall, Run


def save_llm_call(
    *,
    run_id: int,
    ticker: str,
    node_name: str,
    started_at: datetime,
    model: str,
    prompt_text: str,
    response_text: str,
    tool_calls: list | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    duration_ms: int = 0,
) -> int:
    with get_session() as s:
        row = LlmCall(
            run_id=run_id,
            ticker=ticker,
            node_name=node_name,
            started_at=started_at,
            model=model,
            prompt_text=prompt_text,
            response_text=response_text,
            tool_calls_json=json.dumps(tool_calls or []),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id


def llm_calls_for_run(run_id: int) -> list[LlmCall]:
    with get_session() as s:
        return list(
            s.exec(
                select(LlmCall)
                .where(LlmCall.run_id == run_id)
                .order_by(LlmCall.started_at)
            )
        )


def _run_to_dict(r: Run) -> dict:
    return {
        "id": r.id,
        "ticker": r.ticker,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "status": r.status,
        "decision_action": r.decision_action,
        "decision_target": r.decision_target,
        "decision_rationale": r.decision_rationale,
        "decision_confidence": r.decision_confidence,
    }


def list_runs_for_ticker(ticker: str, limit: int = 50) -> list[dict]:
    """Return runs for a ticker as lightweight dicts (no events/llm_calls)."""
    with get_session() as s:
        rows = s.exec(
            select(Run)
            .where(Run.ticker == ticker)
            .order_by(desc(Run.started_at))
            .limit(limit)
        )
        return [_run_to_dict(r) for r in rows]
