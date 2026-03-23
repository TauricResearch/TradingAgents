from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from typing import Dict, Any, List, AsyncGenerator
import logging
import uuid
import time
from agent_os.backend.store import runs
from agent_os.backend.dependencies import get_current_user
from agent_os.backend.services.langgraph_engine import LangGraphEngine

logger = logging.getLogger("agent_os.runs")

router = APIRouter(prefix="/api/run", tags=["runs"])

engine = LangGraphEngine()


async def _run_and_store(run_id: str, gen: AsyncGenerator[Dict[str, Any], None]) -> None:
    """Drive an engine generator, updating run status and caching events."""
    runs[run_id]["status"] = "running"
    runs[run_id]["events"] = []
    try:
        async for event in gen:
            runs[run_id]["events"].append(event)
        runs[run_id]["status"] = "completed"
    except Exception as exc:
        runs[run_id]["status"] = "failed"
        runs[run_id]["error"] = str(exc)
        logger.exception("Run failed run=%s", run_id)


@router.post("/scan")
async def trigger_scan(
    background_tasks: BackgroundTasks, 
    params: Dict[str, Any] = None, 
    user: dict = Depends(get_current_user)
):
    run_id = str(uuid.uuid4())
    runs[run_id] = {
        "id": run_id,
        "type": "scan",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": params or {}
    }
    logger.info("Queued SCAN run=%s user=%s", run_id, user["user_id"])
    background_tasks.add_task(_run_and_store, run_id, engine.run_scan(run_id, params or {}))
    return {"run_id": run_id, "status": "queued"}

@router.post("/pipeline")
async def trigger_pipeline(
    background_tasks: BackgroundTasks, 
    params: Dict[str, Any] = None, 
    user: dict = Depends(get_current_user)
):
    run_id = str(uuid.uuid4())
    runs[run_id] = {
        "id": run_id,
        "type": "pipeline",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": params or {}
    }
    logger.info("Queued PIPELINE run=%s user=%s", run_id, user["user_id"])
    background_tasks.add_task(_run_and_store, run_id, engine.run_pipeline(run_id, params or {}))
    return {"run_id": run_id, "status": "queued"}

@router.post("/portfolio")
async def trigger_portfolio(
    background_tasks: BackgroundTasks, 
    params: Dict[str, Any] = None, 
    user: dict = Depends(get_current_user)
):
    run_id = str(uuid.uuid4())
    runs[run_id] = {
        "id": run_id,
        "type": "portfolio",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": params or {}
    }
    logger.info("Queued PORTFOLIO run=%s user=%s", run_id, user["user_id"])
    background_tasks.add_task(_run_and_store, run_id, engine.run_portfolio(run_id, params or {}))
    return {"run_id": run_id, "status": "queued"}

@router.post("/auto")
async def trigger_auto(
    background_tasks: BackgroundTasks, 
    params: Dict[str, Any] = None, 
    user: dict = Depends(get_current_user)
):
    run_id = str(uuid.uuid4())
    runs[run_id] = {
        "id": run_id,
        "type": "auto",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": params or {}
    }
    logger.info("Queued AUTO run=%s user=%s", run_id, user["user_id"])
    background_tasks.add_task(_run_and_store, run_id, engine.run_auto(run_id, params or {}))
    return {"run_id": run_id, "status": "queued"}

@router.get("/")
async def list_runs(user: dict = Depends(get_current_user)):
    # Filter by user in production
    return list(runs.values())

@router.get("/{run_id}")
async def get_run_status(run_id: str, user: dict = Depends(get_current_user)):
    if run_id not in runs:
        raise HTTPException(status_code=404, detail="Run not found")
    return runs[run_id]
