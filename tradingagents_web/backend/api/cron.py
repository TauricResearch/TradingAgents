from fastapi import APIRouter, Depends
from backend.models.user import User
from backend.api.deps import get_current_user
from backend.services.cron_service import get_cron_service

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.get("/status")
async def cron_status(_: User = Depends(get_current_user)):
    cron = get_cron_service()
    if cron is None:
        return {"running": False, "job_configured": False, "next_run_time": None}
    return cron.get_status()
