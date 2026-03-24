from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from typing import Dict, Any, List, AsyncGenerator
import logging
import uuid
import time
from agent_os.backend.store import runs
from agent_os.backend.dependencies import get_current_user
from agent_os.backend.services.langgraph_engine import LangGraphEngine
from agent_os.backend.services.mock_engine import MockEngine

logger = logging.getLogger("agent_os.runs")

router = APIRouter(prefix="/api/run", tags=["runs"])

engine = LangGraphEngine()
mock_engine = MockEngine()


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

@router.post("/mock")
async def trigger_mock(
    background_tasks: BackgroundTasks,
    params: Dict[str, Any] = None,
    user: dict = Depends(get_current_user),
):
    """Start a mock run that streams scripted events — no real LLM calls.

    Accepted params:
      mock_type : "pipeline" | "scan" | "auto"  (default: "pipeline")
      ticker    : ticker symbol for pipeline / auto  (default: "AAPL")
      tickers   : list of tickers for auto mock
      date      : analysis date  (default: today)
      speed     : delay divisor — 1.0 = realistic, 5.0 = fast  (default: 1.0)
    """
    p = params or {}
    run_id = str(uuid.uuid4())
    runs[run_id] = {
        "id": run_id,
        "type": "mock",
        "status": "queued",
        "created_at": time.time(),
        "user_id": user["user_id"],
        "params": p,
    }
    logger.info(
        "Queued MOCK run=%s mock_type=%s user=%s",
        run_id, p.get("mock_type", "pipeline"), user["user_id"],
    )
    background_tasks.add_task(
        _run_and_store, run_id, mock_engine.run_mock(run_id, p)
    )
    return {"run_id": run_id, "status": "queued"}

@router.delete("/portfolio-stage")
async def reset_portfolio_stage(
    params: Dict[str, Any],
    user: dict = Depends(get_current_user),
):
    """Delete PM decision and execution result for a given date/portfolio_id.

    After calling this, an auto run will re-run Phase 3 from scratch
    (Phases 1 & 2 are skipped if their cached results still exist).
    """
    from tradingagents.portfolio.report_store import ReportStore
    date = params.get("date")
    portfolio_id = params.get("portfolio_id")
    if not date or not portfolio_id:
        raise HTTPException(status_code=422, detail="date and portfolio_id are required")
    store = ReportStore()
    deleted = store.clear_portfolio_stage(date, portfolio_id)
    logger.info("reset_portfolio_stage date=%s portfolio=%s deleted=%s user=%s", date, portfolio_id, deleted, user["user_id"])
    return {"deleted": deleted, "date": date, "portfolio_id": portfolio_id}


@router.get("/")
async def list_runs(user: dict = Depends(get_current_user)):
    # Filter by user in production
    return list(runs.values())

@router.get("/{run_id}")
async def get_run_status(run_id: str, user: dict = Depends(get_current_user)):
    if run_id not in runs:
        raise HTTPException(status_code=404, detail="Run not found")
    return runs[run_id]
