from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from api.auth import get_user_claims_async
from api.scheduler import scheduler

router = APIRouter(tags=["admin"])


@router.post("/signals-ms/generate")
async def force_generate(
    request: Request,
    background_tasks: BackgroundTasks,
    ticker: Optional[str] = Query(
        None, description="Force generation for a specific ticker"
    ),
):
    _, tier = await get_user_claims_async(request)
    if tier != "pro":
        raise HTTPException(status_code=403, detail="Admin/Pro required")
    background_tasks.add_task(scheduler.run_scheduler_cycle, ticker)
    return {
        "status": "triggered",
        "ticker": ticker or "all",
    }
