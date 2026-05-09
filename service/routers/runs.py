"""Runs: create, list, drilldown, cancel, and live-streaming WebSocket."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from gui import storage
from gui.log_browser import discover_logs, load_archive_full
from tradingagents.dataflows.utils import safe_ticker_component
from service.runner_pool import pool
from service.schemas import RunCreateRequest, RunDetail, RunSummary

router = APIRouter(prefix="/runs", tags=["runs"])


# ---------------------------------------------------------------------------
# CRUD-shaped endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=RunSummary)
def create_run(req: RunCreateRequest) -> RunSummary:
    """Start a new analysis run. Returns immediately; the client should
    connect to ``/runs/{run_id}/stream`` to follow."""
    safe_ticker_component(req.ticker)  # validate

    run_id = storage.new_run_id()
    storage.create_run(
        run_id=run_id,
        ticker=req.ticker,
        trade_date=req.trade_date,
        provider=req.llm_provider,
        deep_model=req.deep_think_llm,
        quick_model=req.quick_think_llm,
        backend_url=req.backend_url,
        debate_rounds=req.max_debate_rounds,
        risk_rounds=req.max_risk_discuss_rounds,
        vendors=req.data_vendors,
    )

    job = req.model_dump()
    pool.start(run_id=run_id, job=job)

    db_row = storage.get_run(run_id) or {}
    return RunSummary(**db_row)


@router.get("", response_model=List[RunSummary])
def list_runs(ticker: Optional[str] = None, limit: int = 200) -> List[RunSummary]:
    rows = storage.list_runs(ticker=ticker, limit=limit)
    return [RunSummary(**r) for r in rows]


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str) -> RunDetail:
    row = storage.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="run not found")

    state: dict = {}
    tool_trace: list = []
    log_path = row.get("log_path")
    if log_path and Path(log_path).exists():
        full = load_archive_full(log_path) or {}
        state = full.get("state") or {}
        tool_trace = full.get("tool_trace") or []

    return RunDetail(**row, state=state, tool_trace=tool_trace)


@router.post("/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    if not pool.cancel(run_id):
        raise HTTPException(status_code=404, detail="run not running")
    return {"cancelled": True}


# ---------------------------------------------------------------------------
# History from disk (legacy CLI runs + GUI archives)
# ---------------------------------------------------------------------------

@router.get("/disk/index")
def list_disk_logs() -> JSONResponse:
    """Return every state log discoverable on disk, joined with DB rows."""
    db_by_run_id = {r["run_id"]: r for r in storage.list_runs(limit=10_000)}
    db_by_key = {(r["ticker"], r["trade_date"]): r for r in db_by_run_id.values()}
    entries = discover_logs()
    out = []
    for entry in entries:
        rid = entry.get("run_id", "")
        db = db_by_run_id.get(rid) or db_by_key.get((entry["ticker"], entry["trade_date"])) or {}
        out.append({**entry, "db": db})
    return JSONResponse(out)


# ---------------------------------------------------------------------------
# WebSocket — live stream of agent output
# ---------------------------------------------------------------------------

@router.websocket("/{run_id}/stream")
async def stream_run(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    q = await pool.subscribe(run_id)
    try:
        while True:
            ev = await q.get()
            if ev.get("type") == "_eof":
                break
            await ws.send_text(json.dumps(ev))
    except WebSocketDisconnect:
        pass
    finally:
        pool.unsubscribe(run_id, q)
        try:
            await ws.close()
        except RuntimeError:
            pass
