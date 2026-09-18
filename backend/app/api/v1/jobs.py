import asyncio
import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from sse_starlette.sse import EventSourceResponse

from ...core.config import settings
from ...core.database import db
from ...core.security import sanitize_date, sanitize_ticker
from ...models.schemas import (
    BatchDeleteRequest,
    BatchDeleteResponse,
    ClearJobsResponse,
    DeleteJobResponse,
    JobCreateRequest,
    JobEventItem,
    JobListResponse,
    JobResponse,
)
from ...workers.job_manager import job_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _cleanup_job_report_files(ticker: str, trade_date: str, created_at: str | None = None):
    """Safely remove matching exported report directory from results/reports if present."""
    try:
        clean_ticker = sanitize_ticker(ticker, default="")
        if not clean_ticker:
            return

        reports_root = settings.REPORTS_DIR
        if not reports_root or not reports_root.exists():
            return

        clean_trade_date = "".join(c for c in sanitize_date(trade_date) if c.isdigit())
        clean_created_date = "".join(c for c in sanitize_date((created_at or "")[:10]) if c.isdigit())

        prefixes = []
        if clean_trade_date:
            prefixes.append(f"{clean_ticker}_{clean_trade_date}")
        if clean_created_date and clean_created_date != clean_trade_date:
            prefixes.append(f"{clean_ticker}_{clean_created_date}")

        if not prefixes:
            return

        for folder in reports_root.iterdir():
            if folder.is_dir() and any(folder.name.startswith(p) for p in prefixes):
                shutil.rmtree(folder, ignore_errors=True)
                logger.info(f"Purged report directory {folder.name} for job {ticker}")
    except Exception as e:
        logger.warning(f"Failed to cleanup report directory for {ticker}: {e}")

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

@router.delete("/{job_id}", response_model=DeleteJobResponse)
async def delete_job(
    job_id: str,
    force: bool = Query(False, description="Force cancel and delete if job is running or queued")
):
    """Delete a single job. Cascades automatically to job_events and job_reports."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] in ("running", "queued"):
        if not force:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete job in '{job['status']}' state without force=true. Cancel the job first or pass force=true."
            )
        await job_manager.cancel_job(job_id)

    _cleanup_job_report_files(job.get("ticker", ""), job.get("trade_date", ""), job.get("created_at"))
    success = db.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or already deleted")
    return {"message": "Job deleted successfully", "job_id": job_id}

@router.post("/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_jobs(req: BatchDeleteRequest):
    """Delete multiple jobs in a single batch operation."""
    if not req.job_ids:
        return {"message": "No jobs provided for deletion", "deleted_count": 0, "job_ids": []}

    target_ids: list[str] = []
    for jid in req.job_ids:
        job = db.get_job(jid)
        if not job:
            continue
        if job["status"] in ("running", "queued"):
            if not req.force:
                continue  # Skip active jobs safely
            await job_manager.cancel_job(jid)

        _cleanup_job_report_files(job.get("ticker", ""), job.get("trade_date", ""), job.get("created_at"))
        target_ids.append(jid)

    deleted_count = db.delete_jobs_batch(target_ids)
    return {
        "message": f"Successfully deleted {deleted_count} job(s)",
        "deleted_count": deleted_count,
        "job_ids": target_ids,
    }

ALLOWED_CLEAR_STATUSES = {"completed", "failed", "cancelled"}

@router.delete("", response_model=ClearJobsResponse)
async def clear_jobs_history(
    status: str | None = Query(None, description="Filter status to clear: failed, cancelled, completed"),
    all_finished: bool = Query(False, description="Clear all finished jobs (completed, failed, cancelled)")
):
    """Clear jobs history by status filter or clear all finished jobs."""
    if not status and not all_finished:
        raise HTTPException(
            status_code=400,
            detail="Please specify a 'status' query parameter (e.g. failed, cancelled, completed) or pass 'all_finished=true'."
        )

    if status:
        normalized_status = status.lower().strip()
        if normalized_status in ("running", "queued"):
            raise HTTPException(
                status_code=400,
                detail="Cannot bulk clear active jobs in 'running' or 'queued' status. Cancel or delete them individually."
            )
        if normalized_status not in ALLOWED_CLEAR_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Allowed statuses to clear: {', '.join(sorted(ALLOWED_CLEAR_STATUSES))}."
            )
        deleted_count = db.clear_jobs(status=normalized_status, all_finished=False)
    else:
        deleted_count = db.clear_jobs(status=None, all_finished=True)

    return {
        "message": f"Successfully cleared {deleted_count} job(s)",
        "deleted_count": deleted_count,
    }

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
