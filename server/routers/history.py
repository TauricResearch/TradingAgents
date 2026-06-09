"""Past-run history from the memory log + full state JSON on disk."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

import user_prefs
from tradingagents.agents.utils.memory import TradingMemoryLog
from ..deps import require_auth

router = APIRouter(prefix="/api", tags=["history"])


def _memory_for(email: str) -> TradingMemoryLog:
    home = user_prefs.user_home(email)
    return TradingMemoryLog({"memory_log_path": str(home / "memory" / "trading_memory.md")})


@router.get("/history")
def history(email: str = Depends(require_auth)):
    return _memory_for(email).load_entries()


@router.get("/history/{ticker}/{date}")
def full_state(ticker: str, date: str, email: str = Depends(require_auth)):
    home = user_prefs.user_home(email)
    path = (
        home / "logs" / ticker / "TradingAgentsStrategy_logs"
        / f"full_states_log_{date}.json"
    )
    if not path.exists():
        raise HTTPException(status_code=404, detail="no full state for that run")
    return json.loads(path.read_text(encoding="utf-8"))
