from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.openapi.utils import get_openapi
import uvicorn

from tradingagents_service.api.routes import (
    evaluations_router,
    health_router,
    precedents_router,
    reports_router,
    shadow_runs_router,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


def create_app() -> FastAPI:
    app = FastAPI(
        title="TradingAgents Flint Shadow API",
        version="0.1.0",
        openapi_version="3.0.3",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.include_router(health_router)
    app.include_router(precedents_router)
    app.include_router(shadow_runs_router)
    app.include_router(reports_router)
    app.include_router(evaluations_router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def operator_home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={},
        )

    def _custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
            description=app.description,
        )
        schema["openapi"] = "3.0.3"
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = _custom_openapi
    return app


app = create_app()


def main() -> None:
    uvicorn.run("tradingagents_service.api.app:app", host="0.0.0.0", port=8000, reload=False)
