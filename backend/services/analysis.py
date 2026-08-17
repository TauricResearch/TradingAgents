from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.core.deps import cancel_flag, clear_cancel, get_executor
from backend.integrations.india import normalize_india_symbol
from backend.integrations.normalize import first_paragraphs
from backend.integrations.tradingagents_adapter import TradingAgentsAdapter
from backend.models import AgentResult, Analysis, AnalysisEvent, Decision
from backend.schemas import AnalysisCreate
from backend.services.auth import user_settings
from backend.services.events import event_bus

logger = logging.getLogger(__name__)
adapter = TradingAgentsAdapter()

ALL_AGENTS = [
    "Market Analyst",
    "Sentiment Analyst",
    "News Analyst",
    "Fundamentals Analyst",
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
    "Trader",
    "Aggressive Analyst",
    "Neutral Analyst",
    "Conservative Analyst",
    "Portfolio Manager",
]


def create_analysis(db: Session, user, body: AnalysisCreate) -> Analysis:
    settings = user_settings(user)
    symbol, exchange = normalize_india_symbol(body.symbol)
    analysts = body.selected_analysts or _analysts_from_settings(settings)
    provider = body.llm_provider or settings.get("llm_provider") or "openai"
    model = body.model or settings.get("model") or "gpt-5.5"
    depth = body.research_depth or settings.get("research_depth") or "medium"
    analysis = Analysis(
        user_id=user.id,
        symbol=symbol,
        exchange=exchange,
        analysis_date=body.analysis_date or datetime.now(timezone.utc).date().isoformat(),
        status="queued",
        provider=provider,
        model=model,
        research_depth=depth,
        selected_analysts=",".join(analysts),
    )
    db.add(analysis)
    db.flush()
    for name in ALL_AGENTS:
        db.add(AgentResult(analysis_id=analysis.id, agent_name=name, status="waiting"))
    db.commit()
    db.refresh(analysis)
    get_executor().submit(_run_job, analysis.id, body.model_dump(), settings)
    return analysis


def cancel_analysis(db: Session, analysis: Analysis) -> Analysis:
    if analysis.status in {"completed", "failed", "cancelled"}:
        return analysis
    cancel_flag(analysis.id).set()
    analysis.status = "cancelled"
    analysis.error_message = "Cancelled by user"
    analysis.completed_at = datetime.now(timezone.utc)
    db.commit()
    event_bus.publish(analysis.id, "analysis_failed", {"error": "cancelled"})
    return analysis


def _analysts_from_settings(settings: dict[str, Any]) -> list[str]:
    selected = []
    if settings.get("enable_technical", True):
        selected.append("market")
    if settings.get("enable_sentiment", True):
        selected.append("social")
    if settings.get("enable_news", True):
        selected.append("news")
    if settings.get("enable_fundamentals", True):
        selected.append("fundamentals")
    return selected or ["market"]


def _run_job(analysis_id: str, request: dict[str, Any], settings: dict[str, Any]) -> None:
    from backend.core.db import SessionLocal

    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        if not analysis:
            return
        analysis.status = "running"
        analysis.started_at = datetime.now(timezone.utc)
        db.commit()
        _persist_event(db, analysis_id, "analysis_started", {"symbol": analysis.symbol})
        event_bus.publish(analysis_id, "analysis_started", {"symbol": analysis.symbol})

        config = adapter.build_config(
            llm_provider=request.get("llm_provider") or analysis.provider,
            model=request.get("model") or analysis.model,
            quick_model=request.get("quick_model") or settings.get("quick_model"),
            research_depth=analysis.research_depth,
            debate_rounds=request.get("debate_rounds") or settings.get("debate_rounds"),
            temperature=request.get("temperature") if request.get("temperature") is not None else settings.get("temperature"),
            output_language=settings.get("output_language") or "English",
        )
        flag = cancel_flag(analysis_id)

        def emit(event_type: str, payload: dict[str, Any]) -> None:
            _apply_agent_event(db, analysis_id, event_type, payload)
            _persist_event(db, analysis_id, event_type, payload)
            event_bus.publish(analysis_id, event_type, payload)

        result = adapter.run_analysis(
            symbol=analysis.symbol,
            analysis_date=analysis.analysis_date,
            selected_analysts=analysis.selected_analysts.split(","),
            config=config,
            emit=emit,
            should_cancel=flag.is_set,
        )
        analysis = db.get(Analysis, analysis_id)
        analysis.status = "completed"
        analysis.completed_at = datetime.now(timezone.utc)
        analysis.final_decision = result.get("action")
        analysis.confidence = result.get("confidence")
        analysis.risk_level = result.get("risk_level")
        analysis.payload_json = json.dumps(result, default=str)
        db.add(
            Decision(
                analysis_id=analysis.id,
                action=result.get("action") or "HOLD",
                confidence=result.get("confidence"),
                risk_level=result.get("risk_level"),
                reason=result.get("reason"),
                entry_price=result.get("entry_price"),
                stop_loss=result.get("stop_loss"),
                price_target=result.get("price_target"),
                time_horizon=result.get("time_horizon"),
            )
        )
        for agent in result.get("agents") or []:
            row = (
                db.query(AgentResult)
                .filter(AgentResult.analysis_id == analysis_id, AgentResult.agent_name == agent["agent_name"])
                .first()
            )
            if row:
                row.status = "completed"
                row.summary = agent.get("summary")
                row.structured_output = json.dumps(agent.get("structured_output") or {}, default=str)
                row.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "Analysis completed",
            extra={
                "analysis_id": analysis_id,
                "user_id": analysis.user_id,
                "symbol": analysis.symbol,
                "provider": analysis.provider,
                "model": analysis.model,
                "started_at": str(analysis.started_at),
                "completed_at": str(analysis.completed_at),
                "status": analysis.status,
            },
        )
    except Exception as exc:
        logger.exception(
            "Analysis failed",
            extra={"analysis_id": analysis_id, "error": str(exc), "status": "failed"},
        )
        analysis = db.get(Analysis, analysis_id)
        if analysis:
            analysis.status = "cancelled" if str(exc) == "cancelled" else "failed"
            analysis.error_message = str(exc)
            analysis.completed_at = datetime.now(timezone.utc)
            db.commit()
        event_bus.publish(analysis_id, "analysis_failed", {"error": str(exc)})
        _persist_event(db, analysis_id, "analysis_failed", {"error": str(exc)})
    finally:
        clear_cancel(analysis_id)
        db.close()


def _apply_agent_event(db: Session, analysis_id: str, event_type: str, payload: dict[str, Any]) -> None:
    name = payload.get("agent_name")
    if not name:
        db.commit()
        return
    row = (
        db.query(AgentResult)
        .filter(AgentResult.analysis_id == analysis_id, AgentResult.agent_name == name)
        .first()
    )
    if not row:
        db.commit()
        return
    now = datetime.now(timezone.utc)
    if event_type == "agent_started":
        row.status = "running"
        row.started_at = row.started_at or now
    elif event_type == "agent_completed":
        row.status = "completed"
        row.completed_at = now
        row.summary = first_paragraphs(payload.get("summary"), 2)
        if payload.get("summary"):
            row.structured_output = json.dumps({"full": payload.get("summary")}, default=str)
    db.commit()


def _persist_event(db: Session, analysis_id: str, event_type: str, payload: dict[str, Any]) -> None:
    db.add(AnalysisEvent(analysis_id=analysis_id, event_type=event_type, payload=json.dumps(payload, default=str)))
    db.commit()
