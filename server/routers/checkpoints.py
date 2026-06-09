"""Checkpoint/resume status + clear-all."""
from __future__ import annotations

from fastapi import APIRouter, Depends

import user_prefs
from tradingagents.graph.checkpointer import checkpoint_step, clear_all_checkpoints
from ..deps import require_auth
from ..schemas import OkMessage

router = APIRouter(prefix="/api", tags=["checkpoints"])


def _cache_dir(email: str) -> str:
    return str(user_prefs.user_home(email) / "cache")


@router.get("/checkpoints")
def checkpoint_status(ticker: str, date: str, email: str = Depends(require_auth)):
    step = checkpoint_step(_cache_dir(email), ticker, date)
    return {"ticker": ticker, "date": date, "step": step, "resumable": step is not None}


@router.delete("/checkpoints", response_model=OkMessage)
def clear_checkpoints(email: str = Depends(require_auth)):
    n = clear_all_checkpoints(_cache_dir(email))
    return OkMessage(ok=True, message=f"deleted {n} checkpoint DB(s)")
