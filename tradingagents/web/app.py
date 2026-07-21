"""FastAPI application factory for the TradingAgents web UI.

No ``from __future__ import annotations`` here: FastAPI must evaluate the
``Annotated[..., Depends(...)]`` annotations on the closure-scoped route
functions, and stringified annotations cannot be resolved against closure
locals.
"""

import datetime as _dt
import mimetypes
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from tradingagents import default_config
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.web import (
    history as history_mod,
    providers as providers_mod,
    settings as settings_mod,
)
from tradingagents.web.engine import AnalysisEngine
from tradingagents.web.runs import Run, RunConflictError, RunManager
from tradingagents.web.security import HostAllowlistMiddleware, SecurityHeadersMiddleware

STATIC_DIR = Path(__file__).parent / "static"

ANALYST_ORDER = ["market", "social", "news", "fundamentals"]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Explicit whitelist of non-secret config keys exposed by GET /api/config.
# Never a raw DEFAULT_CONFIG dump: future secret-bearing keys must opt in
# here, so they cannot leak by default. backend_url is deliberately absent
# (secret-adjacent: keyed relays embed tokens in URLs).
CONFIG_WHITELIST = (
    "results_dir",
    "data_cache_dir",
    "memory_log_path",
    "llm_provider",
    "deep_think_llm",
    "quick_think_llm",
    "max_debate_rounds",
    "max_risk_discuss_rounds",
    "output_language",
    "checkpoint_enabled",
    "news_article_limit",
    "global_news_article_limit",
    "global_news_lookback_days",
)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    date: str
    asset_type: Literal["stock", "crypto"] | None = None
    analysts: list[str] = Field(min_length=1)
    research_depth: Literal[1, 3, 5] = 1
    provider: str
    deep_think_llm: str
    quick_think_llm: str
    # Write-only: accepted for openai_compatible relays, never echoed back
    # anywhere and never persisted to web settings.
    backend_url: str | None = None
    google_thinking_level: str | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    output_language: str | None = None
    checkpoint_enabled: bool | None = None


def _validate_run_request(body: RunRequest) -> dict[str, Any]:
    ticker = body.ticker.strip().upper()
    try:
        safe_ticker_component(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    if not _DATE_RE.match(body.date):
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
    try:
        _dt.date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=422, detail="date is not a valid date") from None

    analysts = [a.lower() for a in body.analysts]
    unknown = sorted(set(analysts) - set(ANALYST_ORDER))
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"unknown analysts: {', '.join(unknown)}"
        )
    analysts = [a for a in ANALYST_ORDER if a in set(analysts)]

    provider = body.provider.lower()
    if provider not in providers_mod.PROVIDER_KEYS:
        raise HTTPException(status_code=422, detail=f"unknown provider: {provider}")

    key_error = providers_mod.missing_key_error(provider)
    if key_error:
        raise HTTPException(status_code=422, detail=key_error)

    asset_type = body.asset_type
    if asset_type is None:
        from cli.utils import detect_asset_type

        asset_type = detect_asset_type(ticker)

    return {
        "ticker": ticker,
        "date": body.date,
        "asset_type": asset_type,
        "analysts": analysts,
        "research_depth": body.research_depth,
        "provider": provider,
        "deep_think_llm": body.deep_think_llm,
        "quick_think_llm": body.quick_think_llm,
        "backend_url": body.backend_url,
        "google_thinking_level": body.google_thinking_level,
        "openai_reasoning_effort": body.openai_reasoning_effort,
        "anthropic_effort": body.anthropic_effort,
        "output_language": body.output_language,
        "checkpoint_enabled": body.checkpoint_enabled,
    }


def _run_summary(run: Run) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "state": run.state,
        "draining": run.draining,
        "ticker": run.params.get("ticker"),
        "date": run.params.get("date"),
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "decision": (run.result or {}).get("decision"),
        "error": run.error,
    }


def create_app(engine=None, results_dir: str | None = None) -> FastAPI:
    """Build the web app. ``engine`` is injectable for tests."""
    # Windows registry pollution can map .js to text/plain, which blanks the
    # app (browsers refuse ES modules with a wrong MIME). Register explicitly.
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/javascript", ".mjs")

    manager = RunManager(engine or AnalysisEngine())
    history = history_mod.RunHistory(results_dir or default_config.DEFAULT_CONFIG["results_dir"])

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        # Server exit kills the active run (documented); cancel it cleanly.
        await manager.shutdown()

    app = FastAPI(title="TradingAgents Web", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.manager = manager
    app.state.history = history

    # -- helpers ----------------------------------------------------------

    async def _require_json(request: Request) -> None:
        content_type = request.headers.get("content-type", "")
        if not content_type.lower().startswith("application/json"):
            raise HTTPException(
                status_code=415, detail="state-changing endpoints accept application/json only"
            )

    def _get_run(run_id: str) -> Run:
        run = manager.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run id")
        return run

    def _validated_path(ticker: str, date: str) -> tuple[str, str]:
        try:
            safe_ticker_component(ticker)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        if not _DATE_RE.match(date):
            raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
        return ticker, date

    # -- API --------------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/providers")
    async def providers() -> dict[str, Any]:
        return {"providers": providers_mod.provider_catalog()}

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        effective = {key: default_config.DEFAULT_CONFIG.get(key) for key in CONFIG_WHITELIST}
        return {"config": effective, "last_used": settings_mod.load_settings()}

    @app.get("/api/runs")
    async def list_runs() -> dict[str, Any]:
        entries = history.list_runs()
        active = manager.active_run
        return {
            "runs": entries,
            "active_run": _run_summary(active) if active else None,
        }

    @app.post("/api/runs", status_code=201)
    async def start_run(
        body: RunRequest,
        request: Request,
        _: Annotated[None, Depends(_require_json)],
    ) -> JSONResponse:
        params = _validate_run_request(body)
        try:
            run = manager.start(params)
        except RunConflictError as exc:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "a run is already active",
                    "active_run_id": exc.active_run_id,
                },
            )
        # Persist last-used form settings; save_settings drops backend_url.
        settings_mod.save_settings(
            {k: v for k, v in params.items() if v is not None}
        )
        return JSONResponse(status_code=201, content=_run_summary(run))

    @app.get("/api/runs/{run_id}/events", response_class=EventSourceResponse)
    async def run_events(
        run: Annotated[Any, Depends(_get_run)],
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ):
        after_id = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
        async for event in manager.subscribe(run, after_id=after_id):
            # ServerSentEvent JSON-encodes `data` itself — passing a pre-dumped
            # string here would double-encode and hand the browser a string.
            yield ServerSentEvent(event=event.type, data=event.data, id=str(event.id))

    @app.get("/api/runs/{run_id}")
    async def run_state(run: Annotated[Any, Depends(_get_run)]) -> dict[str, Any]:
        return _run_summary(run)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(
        run: Annotated[Any, Depends(_get_run)],
        _: Annotated[None, Depends(_require_json)],
    ) -> dict[str, Any]:
        manager.cancel(run.id)
        return _run_summary(run)

    @app.get("/api/runs/{ticker}/{date}/report")
    async def run_report(ticker: str, date: str) -> dict[str, Any]:
        ticker, date = _validated_path(ticker, date)
        report = history_mod.load_report(history.results_dir, ticker, date)
        if report is None:
            raise HTTPException(status_code=404, detail="no report for this run")
        return report

    # -- static UI --------------------------------------------------------

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Innermost -> outermost: security headers stamp every response,
    # host allowlist rejects before anything else runs.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(HostAllowlistMiddleware)

    return app
