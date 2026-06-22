"""FastAPI application exposing the engine to the macOS app over localhost.

Endpoints:
  GET  /health                 liveness + schema version (used by the Docker healthcheck and the app)
  GET  /capabilities           provider/model/vendor surface (Settings UI source of truth)
  GET  /journal[?ticker]       decisions journal parsed from the engine memory log
  GET  /reports[?ticker[&date]] list saved run documents, or return one full document
  GET  /search?q=              live ticker/company search (Yahoo Finance public search)
  GET  /prices?ticker=&days=   recent daily closes for the watchlist sparklines
  GET  /openrouter/models      live OpenRouter model catalog (Settings dropdown)
  POST /test                   model availability check (build client + ping)
  POST /test_fred              FRED API key connectivity check
  POST /runs                   start a run; body = resolved run-config JSON; -> {run_id}
  GET  /runs/{id}/events       SSE stream of the run's events (supports Last-Event-ID resume)
  POST /runs/{id}/cancel       request cancellation (checked between graph nodes)
  GET  /runs/{id}/state        terminal status snapshot
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from desk_adapter.protocol import SCHEMA_VERSION
from desk_server.events import sse_format
from desk_server.runner import RunHandle, run_blocking

app = FastAPI(title="TradingDesk engine", version="0.0.1")

_runs: dict[str, RunHandle] = {}

# Runs execute on a dedicated single-worker pool, NOT the event loop's default
# executor. This (a) serializes runs so two concurrent runs never race on the
# shared ``os.environ`` provider keys, and (b) keeps multi-minute runs off the
# default pool that the short /search, /prices, /test endpoints use via
# ``asyncio.to_thread`` — so the UI stays responsive while a run is in flight.
# (A queued run sits at "warming" until the active one finishes.)
_RUN_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="desk-run")

# Evict a finished run from ``_runs`` this long after it completes, so an SSE
# client still has time to drain the tail but the per-run buffer (full report
# markdown + tool output) doesn't accumulate for the container's lifetime.
_RUN_RETENTION_S = 600


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "schema_version": SCHEMA_VERSION, "runs": len(_runs)}


@app.get("/capabilities")
async def capabilities() -> JSONResponse:
    # Imported lazily so /health stays cheap and import errors surface per-call.
    from desk_adapter.introspect import build_capabilities

    return JSONResponse(build_capabilities())


@app.get("/journal")
async def journal(ticker: str | None = None) -> dict:
    """The decisions journal: parsed entries from the engine's memory log.

    Each entry has date, ticker, rating, pending, raw, alpha, holding, decision,
    reflection. Pending entries (raw/alpha None) resolve on a later same-ticker
    run. Powers the app's Ticker Desk journal and watchlist.
    """
    from tradingagents.agents.utils.memory import TradingMemoryLog
    from tradingagents.default_config import DEFAULT_CONFIG

    entries = TradingMemoryLog(DEFAULT_CONFIG).load_entries()
    if ticker:
        entries = [e for e in entries if str(e.get("ticker", "")).upper() == ticker.upper()]
    entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    return {"entries": entries}


@app.get("/reports")
async def reports(ticker: str | None = None, date: str | None = None) -> dict:
    """Saved run documents (the per-run full_states_log JSON).

    With ``ticker`` + ``date``: returns that run's full document (7 report
    sections + bull/bear and 3-way risk transcripts + final decision). With only
    ``ticker`` (or nothing): lists available runs as {ticker, date, rating}.
    """
    import json as _json
    from pathlib import Path

    from tradingagents.agents.utils.rating import parse_rating
    from tradingagents.dataflows.utils import safe_ticker_component
    from tradingagents.default_config import DEFAULT_CONFIG

    results_dir = Path(DEFAULT_CONFIG["results_dir"])

    if ticker and date:
        path = results_dir / safe_ticker_component(ticker) / "TradingAgentsStrategy_logs" / f"full_states_log_{date}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="report not found")
        return _json.loads(path.read_text(encoding="utf-8"))

    out = []
    for path in results_dir.glob("*/TradingAgentsStrategy_logs/full_states_log_*.json"):
        folder = path.parent.parent.name
        if ticker and folder.upper() != safe_ticker_component(ticker).upper():
            continue
        run_date = path.stem.replace("full_states_log_", "")
        rating = ""
        with contextlib.suppress(Exception):
            rating = parse_rating(_json.loads(path.read_text(encoding="utf-8")).get("final_trade_decision", ""))
        out.append({"ticker": folder, "date": run_date, "rating": rating})
    out.sort(key=lambda r: r["date"], reverse=True)
    return {"reports": out}


@app.get("/search")
async def search(q: str = "") -> dict:
    """Live ticker/company search via Yahoo Finance's public search endpoint.

    Powers the app's top-bar command search: real symbols + company names, so
    the user can find and add any listed instrument (no key needed). Returns
    ``{results: [{symbol, name, exchange, type}]}`` ordered by Yahoo relevance.
    """
    import json as _json
    import urllib.parse
    import urllib.request

    query = (q or "").strip()
    if not query:
        return {"results": []}

    def _fetch():
        params = urllib.parse.urlencode({"q": query, "quotesCount": 10, "newsCount": 0})
        url = f"https://query2.finance.yahoo.com/v1/finance/search?{params}"
        # Yahoo rejects the default urllib UA; present a browser-like one.
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) TradingDesk"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = _json.loads(resp.read())
        out = []
        for quote in payload.get("quotes", []):
            symbol = quote.get("symbol")
            if not symbol:
                continue
            out.append(
                {
                    "symbol": symbol,
                    "name": quote.get("shortname") or quote.get("longname") or quote.get("name") or "",
                    "exchange": quote.get("exchDisp") or quote.get("exchange") or "",
                    "type": quote.get("typeDisp") or quote.get("quoteType") or "",
                }
            )
        return out

    try:
        return {"results": await asyncio.to_thread(_fetch)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"search failed: {exc}") from exc


@app.get("/prices")
async def prices(ticker: str = "", days: int = 30) -> dict:
    """Recent daily closing prices for a symbol (watchlist sparklines).

    Uses yfinance (already a dependency); returns ``{points: [close, ...]}``
    oldest→newest. Best-effort: an unknown/illiquid symbol just yields an empty
    list (200), so the row simply shows no sparkline. No key needed.
    """
    symbol = (ticker or "").strip()
    if not symbol:
        return {"points": []}

    def _fetch():
        import yfinance as yf

        hist = yf.Ticker(symbol).history(period=f"{max(days, 5)}d")
        return [float(c) for c in hist["Close"].dropna().tolist()]

    try:
        return {"points": await asyncio.to_thread(_fetch)}
    except Exception:  # noqa: BLE001
        return {"points": []}


@app.get("/openrouter/models")
async def openrouter_models() -> dict:
    """Live OpenRouter model catalog (public endpoint, no key needed)."""
    import json as _json
    import urllib.request

    def _fetch():
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models", headers={"User-Agent": "TradingDesk"}
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = _json.loads(resp.read())
        out = []
        for m in payload.get("data", []):
            mid = m.get("id")
            if mid:
                out.append({"label": m.get("name") or mid, "model_id": mid})
        out.sort(key=lambda x: x["model_id"])
        return out

    try:
        return {"models": await asyncio.to_thread(_fetch)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"could not fetch OpenRouter models: {exc}") from exc


@app.post("/test")
async def test_model(request: Request) -> dict:
    """Quick availability check: build the LLM client and make a tiny call.

    Body: {llm_provider, model, backend_url?, keys?}. Returns {ok} or {ok:false, error}.
    """
    body = await request.json()
    provider = body.get("llm_provider", "")
    model = body.get("model", "")
    base_url = body.get("backend_url")
    keys = {k: v for k, v in (body.get("keys") or {}).items() if v}

    def _ping():
        from tradingagents.llm_clients import create_llm_client

        # Inject the supplied keys only for this check, then restore them — so a
        # /test never leaves a key in the process env for a later run/test.
        saved = {k: os.environ.get(k) for k in keys}
        try:
            os.environ.update(keys)
            client = create_llm_client(provider=provider, model=model, base_url=base_url)
            client.get_llm().invoke("Reply with: OK")
            return True
        finally:
            for k, prior in saved.items():
                if prior is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = prior

    try:
        await asyncio.to_thread(_ping)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}


@app.post("/test_fred")
async def test_fred(request: Request) -> dict:
    """Validate a FRED API key by making one minimal FRED API call."""
    body = await request.json()
    key = body.get("key", "")

    def _ping():
        import json as _json
        import urllib.parse
        import urllib.request

        query = urllib.parse.urlencode({"series_id": "GDP", "api_key": key, "file_type": "json"})
        url = f"https://api.stlouisfed.org/fred/series?{query}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            _json.loads(resp.read())
        return True

    if not key:
        return {"ok": False, "error": "no key"}
    try:
        await asyncio.to_thread(_ping)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


@app.post("/runs")
async def create_run(request: Request) -> dict:
    cfg = await request.json()
    if not cfg.get("ticker") or not cfg.get("trade_date"):
        raise HTTPException(status_code=400, detail="ticker and trade_date are required")
    run_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    handle = RunHandle(run_id, loop)
    _runs[run_id] = handle
    task = loop.run_in_executor(_RUN_EXECUTOR, run_blocking, handle, cfg)
    # Drop the run from _runs a while after it finishes. The done-callback runs
    # on the loop thread, so scheduling call_later from it is thread-safe.
    task.add_done_callback(lambda _t: loop.call_later(_RUN_RETENTION_S, _runs.pop, run_id, None))
    return {"run_id": run_id, "schema_version": SCHEMA_VERSION}


@app.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict:
    handle = _runs.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="unknown run")
    handle.cancelled = True
    return {"cancelled": True}


@app.get("/runs/{run_id}/state")
async def run_state(run_id: str) -> dict:
    handle = _runs.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="unknown run")
    return {"run_id": run_id, "status": handle.status, "done": handle.done, "events": handle.seq}


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    handle = _runs.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="unknown run")

    last = request.headers.get("Last-Event-ID")
    start_idx = int(last) if last and last.isdigit() else 0

    async def gen():
        idx = start_idx
        while True:
            handle.updated.clear()
            while idx < len(handle.events):
                yield sse_format(handle.events[idx])
                idx += 1
            if handle.done and idx >= len(handle.events):
                break
            if await request.is_disconnected():
                break
            try:
                await asyncio.wait_for(handle.updated.wait(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
