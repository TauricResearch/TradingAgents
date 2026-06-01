from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.core.database import get_db
from backend.models.log import SystemLog
from backend.models.user import User
from backend.schemas.log import LogRead
from backend.api.deps import get_current_user

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=list[LogRead])
async def list_logs(
    level: str | None = Query(default=None, description="Filter by level: INFO, WARNING, ERROR, CRITICAL"),
    source: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(SystemLog).order_by(desc(SystemLog.created_at)).limit(limit).offset(offset)
    if level:
        q = q.where(SystemLog.level == level.upper())
    if source:
        q = q.where(SystemLog.source == source)
    result = await db.execute(q)
    return result.scalars().all()
