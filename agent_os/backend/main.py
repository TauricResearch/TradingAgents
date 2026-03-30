from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from agent_os.backend.routes import portfolios, runs, websocket
from agent_os.backend.run_metadata import normalize_run_params
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_os")

app = FastAPI(title="AgentOS API")

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# --- Include Routes ---
app.include_router(portfolios.router)
app.include_router(runs.router)
app.include_router(websocket.router)


def _hydrate_run_record(meta: dict) -> dict:
    """Convert persisted run metadata into an in-memory run record.

    A persisted ``running`` status cannot be resumed after process restart because
    the producer task is gone. Normalize those runs to ``failed`` so the UI sees
    an explicit incomplete state instead of waiting forever for live events.
    """
    status = meta.get("status", "completed")
    error = None
    if status == "running":
        status = "failed"
        error = "Run did not complete (server restarted)"

    record = {
        "id": meta.get("id", ""),
        "type": meta.get("type", ""),
        "status": status,
        "created_at": meta.get("created_at", 0),
        "user_id": meta.get("user_id", "anonymous"),
        "params": normalize_run_params(meta.get("type", ""), meta.get("params", {})),
        "rerun_seq": meta.get("rerun_seq", 0),
        "events": [],  # loaded lazily on demand
        "hydrated_from_disk": True,
    }
    if error:
        record["error"] = error
    return record

@app.on_event("startup")
async def hydrate_runs_from_disk():
    """Populate the in-memory runs store from persisted run_meta.json files."""
    from agent_os.backend.store import runs
    from tradingagents.portfolio.report_store import ReportStore
    try:
        metas = ReportStore.list_run_metas()
        for meta in metas:
            rid = meta.get("id", "")
            if rid and rid not in runs:
                runs[rid] = _hydrate_run_record(meta)
        if metas:
            logger.info("Hydrated %d historical runs from disk", len(metas))
    except Exception:
        logger.exception("Failed to hydrate runs from disk on startup")


@app.get("/")
async def health_check():
    return {"status": "ok", "service": "AgentOS API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8088)
