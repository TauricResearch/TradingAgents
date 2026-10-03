"""The HTTP surface: portfolio CRUD, CSV import, run submission, and a live stream.

Local-first by design. The server binds to the loopback interface and has no
authentication, because it holds a broker's position export and the provider
keys the runs spend money with. Putting it on a public interface would publish
both. Anyone who needs it remotely should tunnel to it rather than bind wide,
and the launcher says so when asked to bind elsewhere.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from cli.models import AnalystType
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS, get_model_options
from tradingagents.memory.log import TradingMemoryLog
from tradingagents.portfolio import PortfolioContext
from webui import store
from webui.importers import parse_positions_csv
from webui.paths import tilde
from webui.runs import DISPLAY_ORDER, RunManager, available_analysts

STATIC_DIR = Path(__file__).parent / "static"

# Analyst keys as the UI labels them. "social" is the wire value the saved
# configs use; "Sentiment" is what the CLI and the reports call it.
ANALYST_LABELS = {
    "market": "Market",
    "social": "Sentiment",
    "news": "News",
    "fundamentals": "Fundamentals",
}


class RunRequest(BaseModel):
    ticker: str
    trade_date: str | None = None
    analysts: list[str] = Field(default_factory=lambda: [a.value for a in AnalystType])
    use_portfolio: bool = True
    llm_provider: str | None = None
    deep_think_llm: str | None = None
    quick_think_llm: str | None = None
    max_debate_rounds: int | None = Field(default=None, ge=1, le=5)
    max_risk_discuss_rounds: int | None = Field(default=None, ge=1, le=5)


class BookRunRequest(BaseModel):
    """Analyze every position in the saved book, as one batch of runs."""

    trade_date: str | None = None
    analysts: list[str] = Field(default_factory=lambda: [a.value for a in AnalystType])
    tickers: list[str] | None = None     # a subset of the book; omit for all of it
    llm_provider: str | None = None
    deep_think_llm: str | None = None
    quick_think_llm: str | None = None
    max_debate_rounds: int | None = Field(default=None, ge=1, le=5)
    max_risk_discuss_rounds: int | None = Field(default=None, ge=1, le=5)


def _settings_from(request) -> dict:
    """The config overrides a request carries, with unset keys left to the config."""
    keys = ("llm_provider", "deep_think_llm", "quick_think_llm",
            "max_debate_rounds", "max_risk_discuss_rounds")
    return {k: getattr(request, k) for k in keys if getattr(request, k) is not None}


def create_app(config: dict | None = None) -> FastAPI:
    config = config or DEFAULT_CONFIG.copy()
    app = FastAPI(title="TradingAgents UI", docs_url="/api/docs", openapi_url="/api/openapi.json")
    manager = RunManager(
        config_factory=lambda: {**DEFAULT_CONFIG, **config},
        portfolio_loader=lambda: store.load(config),
    )
    app.state.manager = manager
    app.state.config = config

    # --- meta ---

    @app.get("/api/config")
    def read_config():
        """What the run form offers: providers, their models, analysts, defaults."""
        return {
            "providers": sorted(MODEL_OPTIONS),
            "models": {
                provider: {
                    mode: [{"label": label, "value": value}
                           for label, value in get_model_options(provider, mode)]
                    for mode in ("quick", "deep")
                }
                for provider in MODEL_OPTIONS
            },
            "analysts": [{"value": v, "label": ANALYST_LABELS[v]} for v in ANALYST_LABELS],
            "report_sections": [{"key": k, "label": label} for k, label in DISPLAY_ORDER],
            "today": get_current_date(),
            "defaults": {
                "llm_provider": config.get("llm_provider"),
                "deep_think_llm": config.get("deep_think_llm"),
                "quick_think_llm": config.get("quick_think_llm"),
                "max_debate_rounds": config.get("max_debate_rounds"),
                "max_risk_discuss_rounds": config.get("max_risk_discuss_rounds"),
                "output_language": config.get("output_language"),
            },
        }

    @app.get("/api/analysts")
    def analysts_for(ticker: str = ""):
        """Analysts the ticker supports: crypto has no filings to analyze."""
        return {"analysts": available_analysts(ticker)}

    # --- portfolio ---

    @app.get("/api/portfolio")
    def read_portfolio():
        """The saved book. ``portfolio: null`` means none is saved, which is not a flat book."""
        book = store.load(config)
        return {
            "portfolio": json.loads(book.model_dump_json()) if book else None,
            "path": tilde(store.portfolio_path(config)),
        }

    @app.put("/api/portfolio")
    def write_portfolio(payload: dict):
        try:
            book = PortfolioContext.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from None
        path = store.save(book, config)
        return {"portfolio": json.loads(book.model_dump_json()), "path": tilde(path)}

    @app.delete("/api/portfolio")
    def delete_portfolio():
        """Remove the book, so runs go back to advice not situated in a position."""
        return {"deleted": store.clear(config)}

    @app.post("/api/portfolio/import")
    async def import_portfolio(request: Request, save: bool = False):
        """Parse a broker CSV into a book. Previews by default; ``?save=true`` commits it.

        The two steps are separate on purpose: a parse that misreads a column
        would otherwise overwrite a book the user typed in by hand, and the
        preview is what makes the skipped rows worth reading.
        """
        body = (await request.body()).decode("utf-8", errors="replace")
        if not body.strip():
            raise HTTPException(status_code=400, detail="no CSV content in the request body")

        result = parse_positions_csv(body)
        if result.is_empty:
            raise HTTPException(
                status_code=422,
                detail={"message": "nothing could be read from this file",
                        "warnings": result.warnings, "skipped": result.skipped},
            )
        path = None
        if save:
            path = tilde(store.save(result.portfolio, config))
        return {
            "portfolio": json.loads(result.portfolio.model_dump_json()),
            "skipped": result.skipped,
            "warnings": result.warnings,
            "saved": save,
            "path": path,
        }

    # --- runs ---

    @app.get("/api/runs")
    def list_runs():
        return {"runs": manager.list()}

    @app.post("/api/runs", status_code=201)
    def create_run(payload: RunRequest):
        try:
            record = manager.submit(
                ticker=payload.ticker,
                trade_date=payload.trade_date or get_current_date(),
                analysts=payload.analysts,
                settings=_settings_from(payload),
                with_portfolio=payload.use_portfolio and store.load(config) is not None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return record.summary()

    @app.post("/api/runs/book", status_code=201)
    def create_book_runs(payload: BookRunRequest):
        """Queue one run per holding. They execute one at a time, in book order."""
        book = store.load(config)
        if book is None or not book.positions:
            raise HTTPException(status_code=400, detail="no saved portfolio with positions")

        wanted = {t.strip().upper() for t in (payload.tickers or [])}
        tickers = [p.ticker.upper() for p in book.positions
                   if not wanted or p.ticker.upper() in wanted]
        if not tickers:
            raise HTTPException(status_code=400, detail="none of those tickers are in the book")

        import uuid

        batch_id = uuid.uuid4().hex[:8]
        settings = _settings_from(payload)
        date = payload.trade_date or get_current_date()
        queued, rejected = [], []
        for ticker in tickers:
            try:
                record = manager.submit(
                    ticker=ticker, trade_date=date, analysts=payload.analysts,
                    settings=settings, with_portfolio=True, batch_id=batch_id,
                )
                queued.append(record.summary())
            except ValueError as exc:
                rejected.append({"ticker": ticker, "reason": str(exc)})
        if not queued:
            raise HTTPException(status_code=400, detail={"rejected": rejected})
        return {"batch_id": batch_id, "runs": queued, "rejected": rejected}

    @app.get("/api/runs/{run_id}")
    def read_run(run_id: str):
        record = manager.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="no such run")
        return record.detail()

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str):
        record = manager.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="no such run")
        return {"cancelled": record.cancel(), "status": record.status}

    @app.get("/api/runs/{run_id}/events")
    async def stream_run(run_id: str, request: Request):
        """Server-sent events for one run, replayed from its first event.

        A reconnecting browser gets the whole run again rather than joining
        mid-stream, which is what makes a reload during a ten-minute analysis
        survivable.
        """
        record = manager.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="no such run")

        sink, backlog = record.subscribe()

        async def events():
            try:
                for event in backlog:
                    yield f"data: {json.dumps(event)}\n\n"
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        # A timeout rather than a blocking get, so a finished
                        # run's stream closes and a dropped client is noticed.
                        event = await asyncio.to_thread(sink.get, True, 1.0)
                    except Exception:
                        if record.status in ("done", "failed", "cancelled") and sink.empty():
                            yield "event: end\ndata: {}\n\n"
                            return
                        yield ": keep-alive\n\n"
                        continue
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                record.unsubscribe(sink)

        return StreamingResponse(events(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    # --- decision history ---

    @app.get("/api/history")
    def read_history(limit: int = 100):
        """Past decisions from the memory log, newest first, with their outcomes."""
        entries = TradingMemoryLog({**DEFAULT_CONFIG, **config}).load_entries()
        return {"entries": [
            {k: e.get(k) for k in ("date", "ticker", "rating", "pending", "raw",
                                   "alpha", "holding", "resolved", "reflection")}
            for e in reversed(entries[-limit:])
        ]}

    # --- static ---

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
