from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.db import engine, get_db
from backend.core.deps import get_admin_user
from backend.models import Analysis, AnalysisEvent, User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health")
def admin_health(db: Session = Depends(get_db), _admin: User = Depends(get_admin_user)):
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {
        "api": "ok",
        "database": "ok" if db_ok else "error",
        "redis": "not_required",
        "tradingagents": "ok",
        "market_data_provider": get_settings().market_data_provider,
        "users": db.query(func.count(User.id)).scalar(),
        "analyses": db.query(func.count(Analysis.id)).scalar(),
    }


@router.get("/users")
def admin_users(db: Session = Depends(get_db), _admin: User = Depends(get_admin_user)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return {
        "items": [
            {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "created_at": u.created_at}
            for u in users
        ]
    }


@router.get("/logs")
def admin_logs(db: Session = Depends(get_db), _admin: User = Depends(get_admin_user)):
    events = db.query(AnalysisEvent).order_by(AnalysisEvent.id.desc()).limit(200).all()
    analyses = db.query(Analysis).order_by(Analysis.created_at.desc()).limit(50).all()
    return {
        "events": [
            {"id": e.id, "analysis_id": e.analysis_id, "type": e.event_type, "payload": e.payload, "created_at": e.created_at}
            for e in events
        ],
        "analyses": [
            {
                "id": a.id,
                "symbol": a.symbol,
                "status": a.status,
                "error": a.error_message,
                "provider": a.provider,
                "model": a.model,
            }
            for a in analyses
        ],
    }
