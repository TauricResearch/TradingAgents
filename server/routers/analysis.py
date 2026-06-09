"""Analysis lifecycle: start, SSE stream, snapshot, cancel."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..deps import require_auth
from ..runs import registry
from ..schemas import AnalysisStartReq, AnalysisStartResp, OkMessage, RunSnapshot

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/start", response_model=AnalysisStartResp)
def start(body: AnalysisStartReq, email: str = Depends(require_auth)):
    try:
        run_id, resumed = registry.start(email, body)
    except RuntimeError as e:
        if str(e) == "at_capacity":
            raise HTTPException(status_code=429, detail="server at capacity")
        raise
    return AnalysisStartResp(run_id=run_id, resumed=resumed)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/{run_id}/stream")
async def stream(run_id: str, email: str = Depends(require_auth)):
    run = registry.get(run_id)
    if run is None or run.email != email:
        raise HTTPException(status_code=404, detail="run not found")

    async def gen():
        offset = 0
        # Replay everything accumulated so far (reconnect / refresh path).
        while True:
            pending = run.events_from(offset)
            for ev in pending:
                offset += 1
                kind = ev.get("kind", "message")
                yield _sse(kind, ev)
            if run.finished and offset >= len(run.events):
                break
            yield ": keepalive\n\n"  # heartbeat (anti-buffering through tunnel)
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/{run_id}", response_model=RunSnapshot)
def snapshot(run_id: str, email: str = Depends(require_auth)):
    run = registry.get(run_id)
    if run is None or run.email != email:
        raise HTTPException(status_code=404, detail="run not found")
    return RunSnapshot(**run.snapshot())


@router.post("/{run_id}/cancel", response_model=OkMessage)
def cancel(run_id: str, email: str = Depends(require_auth)):
    run = registry.get(run_id)
    if run is None or run.email != email:
        raise HTTPException(status_code=404, detail="run not found")
    registry.cancel(run_id)
    return OkMessage(ok=True)
