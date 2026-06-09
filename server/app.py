"""FastAPI app factory for the TradingAgents backend.

Loads .env the same way webui.py does, mounts /api routers, and (when a built
Vue dist exists) serves the SPA at / with history-mode fallback.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / ".env.enterprise", override=False)

from .config import settings  # noqa: E402


def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents API")

    @app.get("/api/health")
    def health():
        return {"ok": True}

    # Routers (imported here so test collection of app.py is cheap).
    from .routers import (  # noqa: E402
        analysis,
        auth,
        checkpoints,
        history,
        meta,
        prefs,
        research,
        telegram,
    )

    for mod in (auth, meta, analysis, research, history, prefs, checkpoints, telegram):
        app.include_router(mod.router)

    _mount_spa(app)
    return app


def _mount_spa(app: FastAPI) -> None:
    """Serve the built Vue SPA at / if present (skipped in tests/dev)."""
    dist = Path(settings.frontend_dist)
    index = dist / "index.html"
    if not index.exists():
        return

    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # API routes are matched before this catch-all by FastAPI ordering.
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(index))


app = create_app()
