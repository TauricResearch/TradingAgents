from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .batch import DEFAULT_ARTIFACT_DIR
from .storage import AnalysisRepository


PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"
DEFAULT_DATA_DIR = Path(os.getenv("TRADINGAGENTS_DASHBOARD_DIR", str(DEFAULT_ARTIFACT_DIR))).resolve()


def create_dashboard_app(data_dir: str | Path = DEFAULT_DATA_DIR) -> FastAPI:
    app = FastAPI(title="TradingAgents Hybrid Dashboard MVP")
    repository = AnalysisRepository(data_dir)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        runs = repository.list_runs()
        latest_generated_at = repository.latest_generated_at()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "request": request,
                "runs": runs,
                "latest_generated_at": latest_generated_at,
                "data_dir": str(Path(data_dir).resolve()),
            },
        )

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def detail(request: Request, run_id: str):
        record = repository.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}")
        return templates.TemplateResponse(
            request,
            "detail.html",
            {
                "request": request,
                "record": record,
            },
        )

    return app


app = create_dashboard_app()
