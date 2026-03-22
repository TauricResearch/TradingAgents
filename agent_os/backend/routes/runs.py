from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from typing import Dict, Any, List
import uuid
import time
from agent_os.backend.store import runs
from agent_os.backend.dependencies import get_current_user
from agent_os.backend.services.langgraph_engine import LangGraphEngine

router = APIRouter(prefix="/api/run", tags=["runs"])

engine = LangGraphEngine()

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
    background_tasks.add_task(engine.run_scan, run_id, params or {})
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
    background_tasks.add_task(engine.run_pipeline, run_id, params or {})
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
    background_tasks.add_task(engine.run_portfolio, run_id, params or {})
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
    background_tasks.add_task(engine.run_auto, run_id, params or {})
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
