"""FastAPI router for the ticker accuracy agent."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from web.server.ticker_agent import orchestrator
from web.server.ticker_agent.capabilities import discover_api_capabilities
from web.server.ticker_agent.missing_capabilities import read_missing
from web.server.ticker_agent.config import AgentConfig, load_config, save_config, config_to_dict
from web.server import storage

router = APIRouter(prefix="/api/ticker-agent", tags=["ticker-agent"])


class AgentConfigIn(BaseModel):
    min_samples: int | None = None
    schedule_interval_h: int | None = None
    max_tickers_per_cycle: int | None = None
    sp500_enabled: bool | None = None
    yahoo_sectors_enabled: bool | None = None
    custom_universe_path: str | None = None


@router.get("/status")
def get_status():
    return orchestrator.status()


@router.post("/run-now")
def run_now():
    result = orchestrator.run_cycle()
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "cycle failed"))
    return result


@router.post("/pause")
def pause():
    orchestrator.pause()
    return {"status": "paused"}


@router.post("/resume")
def resume():
    orchestrator.resume()
    return {"status": "running"}


@router.get("/accuracy-leaderboard")
def get_accuracy_leaderboard():
    state_path = storage.ticker_agent_path("agent_state.json")
    if not state_path.exists():
        return {"scores": {}, "last_evaluated": None}
    import json
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return {"scores": state.get("scores", {}), "last_evaluated": state.get("last_evaluated")}
    except (json.JSONDecodeError, OSError):
        return {"scores": {}, "last_evaluated": None}


@router.get("/activity-log")
def get_activity_log(limit: int = 10):
    return {"entries": orchestrator.activity_log(limit=limit)}


@router.get("/missing-capabilities")
def get_missing_capabilities():
    return {"capabilities": [vars(c) for c in read_missing()]}


@router.get("/capabilities")
def get_capabilities():
    return {"capabilities": [vars(c) for c in discover_api_capabilities()]}


@router.get("/config")
def get_agent_config():
    return config_to_dict(load_config())


@router.put("/config")
def update_agent_config(body: AgentConfigIn):
    cfg = load_config()
    update_data = body.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(cfg, k, v)
    save_config(cfg)
    return config_to_dict(cfg)
