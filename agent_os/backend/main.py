import logging
import os
import socket
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from agent_os.backend.routes import portfolios, runs, websocket
from agent_os.backend.run_metadata import normalize_run_params

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_os")


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
    if meta.get("pending_phase3_decision"):
        record["pending_phase3_decision"] = meta["pending_phase3_decision"]
    if error:
        record["error"] = error
    return record

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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await hydrate_runs_from_disk()
    yield


app = FastAPI(title="AgentOS API", lifespan=lifespan)

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
async def log_requests(request: Request, call_next: Callable[[Request], Any]) -> Response:
    logger.info(f"Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response


# --- Include Routes ---
app.include_router(portfolios.router)
app.include_router(runs.router)
app.include_router(websocket.router)


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    from tradingagents.default_config import DEFAULT_CONFIG
    return {
        "default_portfolio_id": DEFAULT_CONFIG.get("default_portfolio_id", "main_portfolio")
    }

@app.get("/")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "AgentOS API"}


def _agent_os_already_running(host: str, port: int) -> bool:
    """Return True when the target port is serving the AgentOS health endpoint."""
    url = f"http://127.0.0.1:{port}/"
    try:
        timeout = float(os.getenv("AGENT_OS_HEALTHCHECK_TIMEOUT_SEC", "1.0"))
    except ValueError:
        timeout = 1.0
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    return '"service":"AgentOS API"' in body and '"status":"ok"' in body


def _port_is_bound(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("AGENT_OS_HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_OS_PORT", "8088"))

    if _port_is_bound("127.0.0.1", port):
        if _agent_os_already_running(host, port):
            logger.info(
                "AgentOS API is already running on port %s; exiting duplicate startup.",
                port,
            )
            raise SystemExit(0)
        raise SystemExit(f"Port {port} is already in use by another process.")

    uvicorn.run(app, host=host, port=port)
