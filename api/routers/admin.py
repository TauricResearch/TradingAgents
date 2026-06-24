from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Query

from api.scheduler import scheduler

router = APIRouter(tags=["admin"])


@router.post("/signals-ms/generate")
def force_generate(
    background_tasks: BackgroundTasks,
    ticker: Optional[str] = Query(
        None, description="Force generation for a specific ticker"
    ),
):
    background_tasks.add_task(scheduler.run_scheduler_cycle, ticker)
    return {
        "status": "triggered",
        "ticker": ticker or "all",
    }
