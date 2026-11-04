"""The HTTP layer: options for the form, starting a run, polling it, cancelling it.

Kept thin on purpose. Every value the form offers comes from the same tables the
CLI menus use (``cli.prompts._llm_provider_table``, the model catalog, the
analyst choices), so the page cannot drift from the terminal.

The API is local-only by design: it starts paid model runs and reads report
files, so it binds to the loopback address and rejects a request whose Host
header is not a local name (a DNS-rebinding guard).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from cli.models import AnalystType, AssetType
from cli.prompts import (
    OUTPUT_LANGUAGES,
    _llm_provider_table,
    detect_asset_type,
    filter_analysts_for_asset_type,
    normalize_ticker_symbol,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS
from webapp import archive
from webapp.rendering import render_markdown
from webapp.service import RunManager, RunOptions, RunRequestError, today

STATIC_DIR = Path(__file__).parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}

# The languages the CLI's menu offers, so the page and the terminal agree.
LANGUAGES = [{"label": label, "value": value} for label, value in OUTPUT_LANGUAGES]
DEPTHS = [
    {"value": 1, "label": "Shallow", "detail": "Quick research, few debate and strategy rounds"},
    {"value": 3, "label": "Medium", "detail": "Middle ground, moderate debate and strategy rounds"},
    {"value": 5, "label": "Deep", "detail": "Comprehensive research, in-depth debate and strategy rounds"},
]


class RunPayload(BaseModel):
    """The form's answers, as posted by the page."""

    ticker: str
    analysis_date: str | None = None
    analysts: list[str] = Field(default_factory=list)
    asset_type: str | None = None
    research_depth: int = 3
    llm_provider: str | None = None
    backend_url: str | None = None
    quick_think_llm: str | None = None
    deep_think_llm: str | None = None
    output_language: str | None = None
    google_thinking_level: str | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    checkpoint: bool | None = None
    save: bool = True
    html: bool = True
    portfolio: dict | None = None


def _providers() -> list[dict]:
    """The provider menu: display name, key, default endpoint and its key status."""
    rows = []
    for display, key, url in _llm_provider_table():
        env_var = get_api_key_env(key)
        spec = OPENAI_COMPATIBLE_PROVIDERS.get(key)
        rows.append({
            "key": key,
            "label": display,
            "default_url": url,
            "api_key_env": env_var,
            "key_present": bool(env_var and os.environ.get(env_var)),
            "signed_in": key in {"chatgpt"},
            "needs_url": bool(spec and spec.require_base_url),
            "key_optional": bool(spec and spec.key_optional),
        })
    return rows


def _models(provider: str) -> dict:
    """Each tier's models for a provider, from the shared catalog.

    A catalog miss (a provider served over a custom endpoint) offers custom IDs
    only, which is exactly what the CLI does for those providers.
    """
    out = {}
    for mode in ("quick", "deep"):
        try:
            options = get_model_options(provider, mode)
        except KeyError:
            options = [("Custom model ID", "custom")]
        out[mode] = [{"label": label, "value": value} for label, value in options]
    return out


def create_app(manager: RunManager | None = None, results_dir: Path | None = None) -> FastAPI:
    """Build the app; a test passes its own ``RunManager`` to observe runs.

    ``results_dir`` is where the archive looks for reports already on disk; it
    defaults to the configured results directory, so the page reads the same
    folder the CLI and the runs write to.
    """
    runs = manager or RunManager()
    archive_root = Path(results_dir) if results_dir else Path(DEFAULT_CONFIG["results_dir"])

    app = FastAPI(title="TradingAgents Web", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runs = runs

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host and host not in LOCAL_HOSTS:
            return JSONResponse({"detail": "This server only answers local requests."}, status_code=403)
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "today": today()}

    @app.get("/api/options")
    def options() -> dict:
        """Everything the form needs to render, in one round trip."""
        return {
            "providers": _providers(),
            "analysts": [
                {
                    "key": AnalystType.MARKET.value,
                    "label": "Market Analyst",
                    "hint": "Prices, indicators and the technical picture",
                },
                {
                    "key": AnalystType.SOCIAL.value,
                    "label": "Sentiment Analyst",
                    "hint": "StockTwits and Reddit posts",
                },
                {
                    "key": AnalystType.NEWS.value,
                    "label": "News Analyst",
                    "hint": "Company and macro news",
                },
                {
                    "key": AnalystType.FUNDAMENTALS.value,
                    "label": "Fundamentals Analyst",
                    "hint": "Financial statements and ratios",
                },
            ],
            "default_analysts": [a.value for a in filter_analysts_for_asset_type(
                list(AnalystType), AssetType.STOCK)],
            "depths": DEPTHS,
            "languages": LANGUAGES,
            "defaults": {
                "today": today(),
                "llm_provider": DEFAULT_CONFIG["llm_provider"],
                "quick_think_llm": DEFAULT_CONFIG["quick_think_llm"],
                "deep_think_llm": DEFAULT_CONFIG["deep_think_llm"],
                "output_language": DEFAULT_CONFIG["output_language"],
                "research_depth": DEFAULT_CONFIG["max_debate_rounds"],
            },
        }

    @app.get("/api/models/{provider}")
    def models(provider: str) -> dict:
        return {"provider": provider.lower(), **_models(provider)}

    @app.get("/api/detect")
    def detect(ticker: str) -> dict:
        """The canonical symbol and the asset type, so the form can adapt as you type."""
        from cli.prompts import is_valid_ticker_input

        if not is_valid_ticker_input(ticker):
            return {"ticker": ticker, "canonical": None, "asset_type": None, "valid": False}
        canonical = normalize_ticker_symbol(ticker) if ticker.strip() else "SPY"
        asset_type = detect_asset_type(canonical)
        allowed = [a.value for a in filter_analysts_for_asset_type(list(AnalystType), asset_type)]
        return {
            "ticker": ticker,
            "canonical": canonical,
            "asset_type": asset_type.value,
            "available_analysts": allowed,
            "valid": True,
        }

    @app.post("/api/runs", status_code=202)
    def start_run(payload: RunPayload) -> dict:
        options = RunOptions(
            ticker=payload.ticker,
            analysis_date=payload.analysis_date or today(),
            analysts=payload.analysts or None,
            asset_type=payload.asset_type,
            research_depth=payload.research_depth,
            llm_provider=payload.llm_provider,
            backend_url=payload.backend_url,
            quick_think_llm=payload.quick_think_llm,
            deep_think_llm=payload.deep_think_llm,
            output_language=payload.output_language,
            google_thinking_level=payload.google_thinking_level,
            openai_reasoning_effort=payload.openai_reasoning_effort,
            anthropic_effort=payload.anthropic_effort,
            checkpoint=payload.checkpoint,
            save=payload.save,
            html=payload.html,
            portfolio=payload.portfolio,
        )
        try:
            run = runs.start(options)
        except RunRequestError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return run.snapshot()

    @app.get("/api/runs")
    def list_runs() -> dict:
        return {"runs": runs.list()}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        run = runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="no such run")
        return run.snapshot()

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict:
        if runs.get(run_id) is None:
            raise HTTPException(status_code=404, detail="no such run")
        if not runs.cancel(run_id):
            raise HTTPException(status_code=409, detail="the run is not running")
        return {"cancelled": True}

    @app.get("/api/runs/{run_id}/report")
    def report_page(run_id: str):
        """The self-contained HTML report the run wrote, if it wrote one."""
        run = runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="no such run")
        if not run.report_html:
            raise HTTPException(status_code=404, detail="this run has no HTML report")
        path = Path(run.report_html)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="the report file is gone")
        return FileResponse(path, media_type="text/html")

    @app.get("/api/runs/{run_id}/report.md")
    def report_markdown(run_id: str):
        run = runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="no such run")
        if not run.report_markdown:
            raise HTTPException(status_code=404, detail="this run has no markdown report")
        path = Path(run.report_markdown)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="the report file is gone")
        return FileResponse(path, media_type="text/markdown")

    @app.get("/api/archive")
    def list_archive() -> dict:
        """The reports already on disk, so they outlive a server restart."""
        return {"reports": [entry.summary() for entry in archive.list_reports(archive_root)]}

    @app.get("/api/archive/{entry_id:path}/sections")
    def archive_sections(entry_id: str) -> dict:
        """One archived report's agent sections, rendered to safe HTML like a live run's."""
        try:
            sections = archive.read_sections(archive_root, entry_id)
        except archive.ArchivePathError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return {
            "id": entry_id,
            "sections": [
                {
                    "title": section["title"],
                    "markdown": section["markdown"],
                    "html": render_markdown(section["markdown"]),
                }
                for section in sections
            ],
        }

    @app.get("/api/archive/{entry_id:path}/report")
    def archive_report_page(entry_id: str):
        """The archived one-page HTML report."""
        try:
            path = archive.report_file(archive_root, entry_id, html=True)
        except archive.ArchivePathError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return FileResponse(path, media_type="text/html")

    @app.get("/api/archive/{entry_id:path}/report.md")
    def archive_report_markdown(entry_id: str):
        """The archived consolidated markdown report."""
        try:
            path = archive.report_file(archive_root, entry_id, html=False)
        except archive.ArchivePathError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return FileResponse(path, media_type="text/markdown")

    @app.delete("/api/archive/{entry_id:path}")
    def delete_archive_report(entry_id: str, confirm: bool = False) -> dict:
        """Remove one archived report from disk.

        Deleting is not undoable, so a caller must say so explicitly with
        ``?confirm=true``; without it the request is refused rather than
        silently obeyed, so a stray DELETE cannot destroy a report.
        """
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="deleting a report is permanent; repeat the request with ?confirm=true",
            )
        try:
            return archive.delete_report(archive_root, entry_id)
        except archive.ArchivePathError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"could not delete the report: {exc}") from None

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
