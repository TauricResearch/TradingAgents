import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query, status
from sse_starlette.sse import EventSourceResponse

from ...core.database import db
from ...models.schemas import JobCreateRequest, JobEventItem, JobListResponse, JobResponse
from ...workers.job_manager import job_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["Jobs"])

@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(req: JobCreateRequest):
    """Create and trigger a new analysis job."""
    if not req.ticker or not req.ticker.strip():
        raise HTTPException(status_code=400, detail="Ticker cannot be empty")

    job = await job_manager.create_and_start_job(req.model_dump())
    return job

@router.get("", response_model=JobListResponse)
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="Filter by status: queued, running, completed, failed, cancelled")
):
    """List jobs with pagination and status filtering."""
    jobs = db.list_jobs(limit=limit, offset=offset, status=status)
    total = db.count_jobs(status=status)
    return {"jobs": jobs, "total": total}

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Get single job status and metadata."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running or queued job."""
    success = await job_manager.cancel_job(job_id)
    if not success:
        job = db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"message": f"Job is already in {job['status']} state", "status": job["status"]}
    return {"message": "Job cancellation requested", "status": "cancelled"}

@router.get("/{job_id}/history", response_model=list[JobEventItem])
async def get_job_event_history(job_id: str, after_id: int = 0):
    """Retrieve full history of events for a job."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    events = db.get_events(job_id, after_id=after_id)
    return events

@router.get("/{job_id}/events")
async def stream_job_events(job_id: str):
    """Server-Sent Events (SSE) streaming endpoint for live agent updates."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    queue = job_manager.subscribe(job_id)

    async def event_generator():
        # First, replay all historical events already stored in DB
        historical_events = db.get_events(job_id)
        last_id = 0
        for ev in historical_events:
            last_id = max(last_id, ev["id"])
            yield {
                "event": ev["event_type"],
                "data": json.dumps(ev, ensure_ascii=False)
            }

        # If job is already terminal, send terminal marker and close
        current_job = db.get_job(job_id)
        if current_job and current_job["status"] in ("completed", "failed", "cancelled"):
            yield {
                "event": "stream_closed",
                "data": json.dumps({"job_id": job_id, "status": current_job["status"]})
            }
            job_manager.unsubscribe(job_id, queue)
            return

        # Listen for real-time live events from worker
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": ev["event_type"],
                        "data": json.dumps(ev, ensure_ascii=False)
                    }
                    if ev["event_type"] in ("job_completed", "job_failed", "job_cancelled"):
                        break
                except asyncio.TimeoutError:
                    # Send periodic ping to prevent connection timeout
                    yield {"event": "ping", "data": json.dumps({"status": "alive"})}
        except asyncio.CancelledError:
            pass
        finally:
            job_manager.unsubscribe(job_id, queue)

    return EventSourceResponse(event_generator())
