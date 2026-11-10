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
import threading
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
from tradingagents import __version__
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS
from webapp import archive
from webapp.backtest_service import (
    BacktestManager,
    BacktestOptions,
    BacktestRequestError,
)
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


class BacktestPayload(BaseModel):
    """The backtest form's answers, as posted by the page."""

    tickers: list[str] = Field(default_factory=list)
    start_date: str
    end_date: str
    every_n_days: int = 7
    analysts: list[str] = Field(default_factory=list)
    asset_type: str = "stock"
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


def create_app(manager: RunManager | None = None, results_dir: Path | None = None,
               backtests: BacktestManager | None = None) -> FastAPI:
    """Build the app; a test passes its own ``RunManager`` to observe runs.

    ``results_dir`` is where the archive looks for reports already on disk; it
    defaults to the configured results directory, so the page reads the same
    folder the CLI and the runs write to.
    """
    runs = manager or RunManager()
    sweeps = backtests or BacktestManager()
    archive_root = Path(results_dir) if results_dir else Path(DEFAULT_CONFIG["results_dir"])

    app = FastAPI(title="TradingAgents Web", docs_url=None, redoc_url=None, openapi_url=None)
    from webapp.usage_api import router as usage_router
    app.include_router(usage_router)
    app.state.runs = runs
    app.state.backtests = sweeps

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host and host not in LOCAL_HOSTS:
            return JSONResponse({"detail": "This server only answers local requests."}, status_code=403)
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict:
        """Liveness plus what build is actually serving (§2 of the P1 task).

        The data lineage audit could not tell from the outside whether a restart
        had happened: a process started before a merge keeps its old modules.
        Reporting the commit and the moment this process loaded makes a stale
        deployment visible instead of guessed at.

        ``version`` is the package version the page shows in its header, so a
        browser tab can be matched to the build it is served by; ``build`` adds
        the commit and the load time, which tell a stale process apart.
        """
        from tradingagents.build_info import build_info

        return {
            "status": "ok",
            "today": today(),
            "version": __version__,
            "build": build_info(),
        }

    @app.get("/api/options")
    def options() -> dict:
        """Everything the form needs to render, in one round trip."""
        return {
            "version": __version__,
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

    # ------------------------------------------------------------- backtest --

    @app.post("/api/backtests", status_code=202)
    def start_backtest(payload: BacktestPayload) -> dict:
        """Start one sweep over the ticker × date grid, in its own thread."""
        options = BacktestOptions(
            tickers=payload.tickers,
            start_date=payload.start_date,
            end_date=payload.end_date,
            every_n_days=payload.every_n_days,
            analysts=payload.analysts,
            asset_type=payload.asset_type,
            portfolio=payload.portfolio,
        )
        try:
            sweep = sweeps.start(options, DEFAULT_CONFIG)
        except BacktestRequestError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return sweep.snapshot()

    @app.get("/api/backtests")
    def list_backtests() -> dict:
        return {"backtests": sweeps.list()}

    @app.get("/api/backtests/{run_id}")
    def get_backtest(run_id: str) -> dict:
        sweep = sweeps.get(run_id)
        if sweep is None:
            raise HTTPException(status_code=404, detail="no such backtest")
        return sweep.snapshot()

    @app.post("/api/backtests/{run_id}/cancel")
    def cancel_backtest(run_id: str) -> dict:
        if sweeps.get(run_id) is None:
            raise HTTPException(status_code=404, detail="no such backtest")
        if not sweeps.cancel(run_id):
            raise HTTPException(status_code=409, detail="the backtest is not running")
        return {"cancelled": True}

    # ---------------------------------------------------------- decision log --

    @app.get("/api/memory")
    def memory_entries() -> dict:
        """The decision log: every recorded decision and, once settled, its outcome."""
        from webapp import memory_view

        return memory_view.list_entries()

    @app.post("/api/memory/settle", status_code=202)
    def memory_settle() -> dict:
        """Settle pending decisions whose holding window has now traded.

        The pass fetches prices and asks the model for a reflection, so it runs
        in its own thread; the page polls ``/api/memory/settle/status``.
        """
        from webapp import memory_view

        with memory_view._SETTLE_LOCK:
            if memory_view._settle_job["status"] == "running":
                raise HTTPException(status_code=409, detail="a settlement pass is already running")
        thread = threading.Thread(target=memory_view.settle, name="memory-settle", daemon=True)
        thread.start()
        return {"status": "running"}

    @app.get("/api/memory/settle/status")
    def memory_settle_status() -> dict:
        from webapp import memory_view

        return memory_view.settle_status()

    # ----------------------------------------------------------------- chart --

    @app.get("/api/chart/{ticker}")
    def chart(ticker: str, date: str) -> dict:
        """Daily closes around the analysis date, point-in-time, for the page's chart."""
        from webapp import chart as chart_module

        try:
            canonical = normalize_ticker_symbol(ticker) if ticker.strip() else "SPY"
            return chart_module.closes_for_chart(canonical, date)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

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
    def report_markdown(run_id: str, download: bool = False):
        run = runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="no such run")
        if not run.report_markdown:
            raise HTTPException(status_code=404, detail="this run has no markdown report")
        path = Path(run.report_markdown)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="the report file is gone")
        # inline by default so the "Markdown" link still opens in a tab;
        # ?download=1 switches to attachment so the download button saves it.
        disposition = "attachment" if download else "inline"
        filename = f"{safe_ticker_component(run.ticker)}_{run.analysis_date}_report.md"
        return FileResponse(
            path, media_type="text/markdown",
            headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
        )

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
    def archive_report_markdown(entry_id: str, download: bool = False):
        """The archived consolidated markdown report."""
        try:
            path = archive.report_file(archive_root, entry_id, html=False)
        except archive.ArchivePathError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        disposition = "attachment" if download else "inline"
        filename = path.name
        return FileResponse(
            path, media_type="text/markdown",
            headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
        )

    @app.get("/api/archive/{entry_id:path}/rerun")
    def archive_rerun(entry_id: str):
        """The settings a report's header records, for pre-filling the form."""
        try:
            return archive.rerun_settings(archive_root, entry_id)
        except archive.ArchivePathError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.get("/api/archive/compare")
    def archive_compare(left: str, right: str) -> dict:
        """Two reports' sections paired by agent, for reading them side by side."""
        try:
            rows = archive.compare_sections(archive_root, left, right)
        except archive.ArchivePathError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return {
            "left": left,
            "right": right,
            "sections": [
                {
                    "title": row["title"],
                    "left_html": render_markdown(row["left"]) if row["left"] else None,
                    "right_html": render_markdown(row["right"]) if row["right"] else None,
                }
                for row in rows
            ],
        }

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
