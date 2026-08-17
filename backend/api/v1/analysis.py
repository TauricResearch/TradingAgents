from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.deps import get_current_user
from backend.models import Analysis, User
from backend.schemas import AnalysisCreate, AnalysisQueued
from backend.services.analysis import cancel_analysis, create_analysis
from backend.services.events import event_bus, sse_pack
from backend.services.serialize import serialize_analysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("", response_model=AnalysisQueued)
def start_analysis(
    body: AnalysisCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analysis = create_analysis(db, user, body)
    return AnalysisQueued(analysis_id=analysis.id, status=analysis.status)


@router.get("")
def list_analysis(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    symbol: str | None = None,
    decision: str | None = None,
):
    query = db.query(Analysis).filter(Analysis.user_id == user.id).order_by(Analysis.created_at.desc())
    if symbol:
        query = query.filter(Analysis.symbol == symbol.upper())
    rows = query.limit(100).all()
    items = [serialize_analysis(row, include_payload=False) for row in rows]
    if decision:
        items = [item for item in items if (item.final_decision or "").upper() == decision.upper()]
    return {"items": items}


@router.get("/{analysis_id}")
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analysis = db.get(Analysis, analysis_id)
    if not analysis or (analysis.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Analysis not found")
    return serialize_analysis(analysis)


@router.post("/{analysis_id}/cancel")
def cancel(
    analysis_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analysis = db.get(Analysis, analysis_id)
    if not analysis or analysis.user_id != user.id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return serialize_analysis(cancel_analysis(db, analysis), include_payload=False)


@router.get("/{analysis_id}/events")
async def analysis_events(analysis_id: str):
    async def gen():
        async for event in event_bus.subscribe(analysis_id):
            yield sse_pack(event)
            if event.get("type") in {"analysis_completed", "analysis_failed"}:
                break

    return StreamingResponse(gen(), media_type="text/event-stream")
