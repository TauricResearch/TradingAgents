"""TradingAgents Web — FastAPI application entry point."""
# ── MUST be before ANY tradingagents import ─────────────────────────────────
# analysis.py and watchlist.py import from tradingagents at module level, so
# this block must run before those imports (i.e. at the top of main.py).
import os as _os, sys as _sys, tempfile as _tf, types as _types

_TMP = _tf.gettempdir()
_os.environ.setdefault("TRADINGAGENTS_LOG_DIR",         _TMP)
_os.environ.setdefault("TRADINGAGENTS_DATA_CACHE_DIR",  _os.path.join(_TMP, "ta_cache"))
_os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR",     _os.path.join(_TMP, "ta_results"))
_os.environ.setdefault("TRADINGAGENTS_MEMORY_LOG_PATH", _os.path.join(_TMP, "ta_memory.md"))

# The vendored, web-adapted agent package lives at backend/trading_agents but
# imports itself as top-level `tradingagents`. Inject a stub for its
# logging_config so __init__.py's setup_unified_logging() becomes a no-op
# (it calls root_logger.handlers.clear(), which would wipe our console + DB log
# handlers). FastAPI/uvicorn own logging here.
_lc_stub = _types.ModuleType("tradingagents.agents.utils.logging_config")
_lc_stub.setup_unified_logging = lambda: None  # type: ignore[attr-defined]
_sys.modules.setdefault("tradingagents.agents.utils.logging_config", _lc_stub)

# ── Make backend/trading_agents authoritative as `tradingagents` ─────────────
# The package directory is `trading_agents` (underscore) but every import — both
# the web layer and the package's own internals — uses the name `tradingagents`.
# This meta-path finder maps the `tradingagents` import name onto the local
# directory and is inserted at the FRONT of sys.meta_path so the local copy wins
# over any pip-installed `tradingagents`. The stub above still takes precedence
# for logging_config (sys.modules is consulted before any finder).
import importlib.abc as _ilab, importlib.util as _ilu


class _LocalTradingAgentsFinder(_ilab.MetaPathFinder):
    _root = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "trading_agents")

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "tradingagents" and not fullname.startswith("tradingagents."):
            return None
        base = _os.path.join(self._root, *fullname.split(".")[1:])
        if _os.path.isdir(base):
            init = _os.path.join(base, "__init__.py")
            if _os.path.isfile(init):
                return _ilu.spec_from_file_location(
                    fullname, init, submodule_search_locations=[base],
                )
            # PEP 420 namespace package (no __init__.py) — the package ships
            # some dirs this way, e.g. tradingagents.agents.utils.
            import importlib.machinery as _ilm
            spec = _ilm.ModuleSpec(fullname, loader=None, is_package=True)
            spec.submodule_search_locations = [base]
            return spec
        pyfile = base + ".py"
        if _os.path.isfile(pyfile):
            return _ilu.spec_from_file_location(fullname, pyfile)
        return None


if not any(isinstance(_f, _LocalTradingAgentsFinder) for _f in _sys.meta_path):
    _sys.meta_path.insert(0, _LocalTradingAgentsFinder())
# ─────────────────────────────────────────────────────────────────────────────

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from backend.core.config import get_settings
from backend.core.database import create_all_tables
from backend.core.security import decode_token
from backend.core.websocket import ws_manager
from backend.services.cron_service import init_cron_service

from backend.api.auth import router as auth_router
from backend.api.analysis import router as analysis_router
from backend.api.watchlist import router as watchlist_router
from backend.api.portfolio import router as portfolio_router
from backend.api.settings import router as settings_router
from backend.api.logs import router as logs_router
from backend.api.cron import router as cron_router
from backend.api.trading import router as trading_router
from backend.api.meta import router as meta_router

# Ensure all models are registered with SQLAlchemy metadata before create_all_tables
import backend.models.portfolio_analysis  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
_logger = logging.getLogger(__name__)
settings = get_settings()

# Import after basicConfig so the handler attaches to the root logger correctly
from backend.core.log_handler import db_log_handler  # noqa: E402
from backend.core.log_redaction import install_redaction  # noqa: E402

# Scrub secrets from every root handler (console + async DB handler) so API
# keys can never reach the terminal or the system_logs table.
install_redaction(*logging.getLogger().handlers)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _logger.info("Starting TradingAgents Web API...")
    await create_all_tables()
    await _seed_admin_user()

    # Start async DB log handler (writes Python logs → system_logs table)
    await db_log_handler.start()

    cron = init_cron_service()
    await _load_cron_settings(cron)
    cron.start()
    _logger.info("Application ready.")

    yield

    # Shutdown
    cron.stop()
    _logger.info("Application stopped.")
    db_log_handler.stop()   # drain remaining buffered logs to DB


async def _seed_admin_user():
    """Create admin user from .env on first run if it doesn't exist."""
    from sqlalchemy import select
    from backend.core.database import AsyncSessionLocal
    from backend.core.security import hash_password
    from backend.models.user import User

    if not settings.ADMIN_USERNAME:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == settings.ADMIN_USERNAME))
        if result.scalar_one_or_none() is None:
            hashed = settings.ADMIN_PASSWORD_HASH or hash_password("changeme")
            db.add(User(username=settings.ADMIN_USERNAME, hashed_password=hashed))
            await db.commit()
            _logger.info("Admin user created: %s", settings.ADMIN_USERNAME)


async def _load_cron_settings(cron):
    """Load cron config from DB on startup."""
    try:
        from sqlalchemy import select
        from backend.core.database import AsyncSessionLocal
        from backend.models.settings import AppSettings

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
            app_settings = result.scalar_one_or_none()
            if app_settings:
                await cron.apply_settings(app_settings)
    except Exception as e:
        _logger.warning("Could not load cron settings: %s", e)


app = FastAPI(
    title="TradingAgents Web API",
    version="1.0.0",
    description="AI-powered trading dashboard with simulation and live trading support",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(auth_router)
app.include_router(analysis_router)
app.include_router(watchlist_router)
app.include_router(portfolio_router)
app.include_router(settings_router)
app.include_router(logs_router)
app.include_router(cron_router)
app.include_router(trading_router)
app.include_router(meta_router)


@app.websocket("/ws/analysis/{task_id}")
async def websocket_analysis(
    websocket: WebSocket,
    task_id: str,
    token: str = Query(..., description="JWT access token"),
):
    """Stream analysis progress events to the browser."""
    # Validate JWT before accepting the WebSocket
    try:
        decode_token(token, expected_type="access")
    except ValueError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await ws_manager.connect(task_id, websocket)
    try:
        # Keep connection open; analysis_service pushes events via ws_manager.send()
        while True:
            await websocket.receive_text()  # absorb client pings
    except WebSocketDisconnect:
        ws_manager.disconnect(task_id, websocket)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve React frontend static files (production build)
_static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        index = os.path.join(_static_dir, "index.html")
        return FileResponse(index)
