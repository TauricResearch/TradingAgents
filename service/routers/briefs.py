"""Brief generation + cache."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from gui import brief as brief_mod
from gui import storage
from gui.log_browser import load_log
from service.schemas import BriefResponse

router = APIRouter(prefix="/runs", tags=["briefs"])


@router.get("/{run_id}/brief", response_model=BriefResponse)
def get_brief(run_id: str) -> BriefResponse:
    cached = brief_mod.get_cached_brief(run_id)
    return BriefResponse(run_id=run_id, brief=cached, cached=cached is not None)


@router.post("/{run_id}/brief", response_model=BriefResponse)
def generate_brief(run_id: str, force: bool = False) -> BriefResponse:
    """Generate (or regenerate) the brief for a run.

    ``force=true`` skips the cache and re-runs the LLM call. Default
    behaviour returns the cached brief if one exists.
    """
    if not force:
        cached = brief_mod.get_cached_brief(run_id)
        if cached is not None:
            return BriefResponse(run_id=run_id, brief=cached, cached=True)

    row = storage.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    log_path = row.get("log_path")
    if not log_path or not Path(log_path).exists():
        raise HTTPException(
            status_code=409,
            detail="run has no on-disk transcript yet — wait for it to finish",
        )
    state = load_log(log_path)
    if state is None:
        raise HTTPException(status_code=500, detail="could not parse run state log")

    meta = {
        "ticker": row["ticker"],
        "trade_date": row["trade_date"],
        "decision": row.get("decision"),
        "run_id": run_id,
    }
    try:
        new_brief = brief_mod.generate_brief(state, meta)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"brief generation failed: {e}")
    brief_mod.store_brief(run_id, new_brief)
    return BriefResponse(run_id=run_id, brief=new_brief, cached=False)
