"""FastAPI application factory for the TradingAgents dashboard."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import storage, queries, events, llm_calls, runner, settings as settings_mod
from tradingagents.default_config import DEFAULT_CONFIG


log = logging.getLogger(__name__)


# Set of currently-open WebSocket objects. Tracked so the lifespan teardown
# can force-close them; otherwise a handler stuck in `ws.receive()` will keep
# the ASGI portal from closing cleanly.
_active_ws: set[WebSocket] = set()


# --------- request/response models ---------

class WatchlistIn(BaseModel):
    ticker: str
    company_name: str = ""
    exchange: str = ""


class WatchlistReorderIn(BaseModel):
    tickers: list[str]


class WatchlistUpdateIn(BaseModel):
    group: str | None = None


class RunIn(BaseModel):
    ticker: str
    force: bool = False


# --------- lifespan ---------

def _price_broadcast(event: dict) -> None:
    """Sync adapter: ``PriceFeed.start`` expects a sync broadcast callable,
    but ``events._broadcast`` is async (it awaits ``ws.send_json``). We
    schedule the async broadcast on the feed's running loop so price
    ticks still fan out to WS global subscribers in production.
    No-op when called outside a running event loop (e.g. from tests
    that drive the poll loop synchronously with broadcast=None)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(events._broadcast(event))


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = settings_mod.get_settings()
    # Hardcoded legacy path: pre-Task-3 default was ~/.tradingagents/dashboard.db.
    # Remove if present so file-based storage starts truly fresh.
    legacy_db = Path.home() / ".tradingagents" / "dashboard.db"
    if legacy_db.exists():
        log.warning("removing legacy SQLite DB at %s (file-based storage only)", legacy_db)
        try:
            legacy_db.unlink()
        except OSError as exc:
            log.error("failed to remove legacy DB: %s", exc)
    storage.init_settings(data_dir=s.data_dir, cache_dir=s.cache_dir)
    # Capture the main event loop so events.emit() (called from worker
    # threads inside loop.run_in_executor) can schedule broadcasts on it
    # via asyncio.run_coroutine_threadsafe. Without this, live WS
    # updates from inside a run silently never fire — the UI only
    # updated on reconnect (replay from events.jsonl).
    events.set_event_loop(asyncio.get_running_loop())
    # Silence yfinance's own ERROR-level noise for delisted/foreign symbols
    # (e.g. "TA125: possibly delisted"). Without this, the dashboard log
    # fills with yfinance-internal tracebacks every poll for every bad
    # ticker in the watchlist.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    # Mark any previously-running runs as failed (process restart recovery).
    for td in storage.walk_data_dir():
        for sd in td.iterdir():
            if not sd.is_dir():
                continue
            rj = storage.read_json(sd / "run.json")
            if rj and rj.get("status") == "running":
                storage.mark_run_status(
                    rj["id"],
                    status="failed",
                    finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                )
                log.warning("reaped stale running run %s", rj["id"])

    # Price-feed state. We always materialise ``PriceState`` on
    # ``app.state`` so ``GET /api/prices`` has something to read (the
    # frontend polls it on first paint, before any ticker exists — an
    # empty ``{}`` is the correct response, not a 404).
    #
    # The background ``PriceFeed`` itself is opt-in via env var so the
    # test suite can disable the network-touching yfinance poll loop.
    from . import price_feed as _pf
    app.state.price_state = _pf.PriceState(
        snapshots={},
        tickers=lambda: [r["ticker"] for r in queries.read_watchlist()],
    )
    if os.environ.get("TRADINGAGENTS_DASHBOARD_DISABLE_PRICE_FEED") != "1":
        feed = _pf.PriceFeed(app.state.price_state, poll_s=s.price_poll_s)
        feed.start(broadcast=_price_broadcast)
        app.state.price_feed = feed

    # Start the runner worker.
    await runner.start()

    # Auto-resume any background past-runs that were running when the
    # server last exited. Runs in the orchestrator's own threads;
    # the server startup is not blocked.
    from web.server import background_runs
    background_runs._load_existing_jobs()

    # Warm the free-keys cache asynchronously so it's fresh when the
    # user opens the settings panel — runs in background, doesn't
    # block server startup.
    asyncio.create_task(_warm_free_keys_cache())

    yield
    # Stop the price feed (if it was started) before the runner so any
    # in-flight poll iteration can complete without racing shutdown.
    feed = getattr(app.state, "price_feed", None)
    if feed is not None:
        await feed.stop()
    await runner.stop()


# ── Free LLM Keys Fetcher (module-level helpers shared by multiple routes) ──

_FREE_KEYS_README_URL = "https://raw.githubusercontent.com/alistaitsacle/free-llm-api-keys/main/README.md"
_FREE_KEYS_API_BASE = "https://aiapiv2.pekpik.com/v1"


def _parse_free_key_tables(text: str) -> list[dict]:
    entries: list[dict] = []
    current_section = None
    in_table_body = False

    for line in text.split("\n"):
        m = re.match(r'^###\s+(.+?)\s+`(.+?)`\s*$', line)
        if m:
            current_section = m.group(1).strip()
            in_table_body = False
            continue

        if line.strip().startswith("| Key | Model | Status |"):
            in_table_body = True
            continue
        if line.strip().startswith("|---"):
            continue

        if in_table_body and line.strip().startswith("|"):
            m2 = re.match(
                r'\|\s*`(sk-[a-zA-Z0-9]+)`\s*\|\s*(.+?)\s*\|\s*.+?\s*\|\s*\$?(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|',
                line,
            )
            if m2 and current_section:
                entries.append({
                    "key": m2.group(1).strip(),
                    "model": m2.group(2).strip(),
                    "provider": current_section,
                    "budget": f"${m2.group(3).strip()}",
                    "rate_limit": m2.group(4).strip(),
                    "expires": m2.group(5).strip(),
                    "description": m2.group(6).strip(),
                    "masked_key": "",
                    "status": "unknown",
                    "test_response": None,
                    "error_message": None,
                })
        else:
            in_table_body = False

    return entries


async def _test_one_key(entry: dict, base_url: str) -> dict:
    """Test a single free key. Returns the entry with status / test fields populated."""
    result = dict(entry)
    try:
        payload = {
            "model": entry["model"],
            "messages": [{"role": "user", "content": "Say hi"}],
            "max_tokens": 5,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {entry['key']}",
                },
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                c = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                result["status"] = "working"
                result["test_response"] = (c or "")[:50]
            else:
                try:
                    err_body = resp.json()
                    msg = ""
                    if isinstance(err_body, dict):
                        err = err_body.get("error") or {}
                        raw = err.get("message") if isinstance(err, dict) else str(err_body)
                        msg = str(raw) if raw else ""
                    result["error_message"] = msg[:200]
                    lower = msg.lower() if msg else ""
                    if any(kw in lower for kw in ("credit balance", "insufficient credit", "can only afford", "never purchased")):
                        result["status"] = "low_balance"
                    elif any(kw in lower for kw in ("no access", "suspended")):
                        result["status"] = "no_access"
                    elif "rate limit" in lower:
                        result["status"] = "rate_limited"
                    else:
                        result["status"] = "error"
                except Exception:
                    result["status"] = "error"
                    result["error_message"] = f"HTTP {resp.status_code}"
    except Exception as e:
        result["status"] = "error"
        result["error_message"] = str(e)[:100]
    return result


def _cache_free_keys(results: list[dict]) -> None:
    """Write the sorted key list + timestamp to the disk cache."""
    cache_path = storage.data_dir() / "free_llm_keys_cache.json"
    storage.write_json_atomic(cache_path, {
        "saved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "keys": results,
        "base_url": _FREE_KEYS_API_BASE,
    })


async def _warm_free_keys_cache() -> None:
    """Fetch, test, and cache free keys in the background at startup."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_FREE_KEYS_README_URL)
            resp.raise_for_status()
            text = resp.text
    except Exception:
        log.warning("free-keys warm: failed to fetch README, skipping")
        return

    entries = _parse_free_key_tables(text)
    if not entries:
        _cache_free_keys([])
        return

    results: list[dict] = []
    sem = asyncio.Semaphore(10)

    async def _test_and_mask(entry: dict) -> dict:
        async with sem:
            r = await _test_one_key(entry, _FREE_KEYS_API_BASE)
        k = r["key"]
        r["masked_key"] = f"{k[:10]}...{k[-4:]}" if len(k) > 14 else k
        return r

    tasks = [_test_and_mask(e) for e in entries]
    for coro in asyncio.as_completed(tasks):
        results.append(await coro)

    status_rank = {"working": 0, "low_balance": 1, "rate_limited": 2, "no_access": 3, "error": 4, "unknown": 5}
    results.sort(key=lambda r: (status_rank.get(r["status"], 99), r["provider"], r["model"]))
    _cache_free_keys(results)
    log.info("free-keys warm: cached %d keys (%d working)", len(results), sum(1 for r in results if r["status"] == "working"))


def create_app() -> FastAPI:
    # Load .env into os.environ at startup so user-saved config (model,
    # provider, api key) is picked up by the trading graph on every run
    # without restarting the server process.
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if _env_path.exists():
        for _line in _env_path.read_text(encoding="utf-8").splitlines():
            _s = _line.strip()
            if _s and not _s.startswith("#") and "=" in _s:
                _k, _, _v = _s.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

    app = FastAPI(title="TradingAgents Dashboard", lifespan=lifespan)

    @app.get("/api/config/models")
    def config_models():
        env = _read_dotenv()
        return {
            "llm_provider": os.environ.get("TRADINGAGENTS_LLM_PROVIDER") or env.get("TRADINGAGENTS_LLM_PROVIDER") or DEFAULT_CONFIG.get("llm_provider"),
            "deep_think_model": os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM") or env.get("TRADINGAGENTS_DEEP_THINK_LLM") or DEFAULT_CONFIG.get("deep_think_llm"),
            "quick_think_model": os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM") or env.get("TRADINGAGENTS_QUICK_THINK_LLM") or DEFAULT_CONFIG.get("quick_think_llm"),
        }

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "uptime_s": 0,
            "watchlist_size": len(queries.read_watchlist()),
            "runs_in_queue": 0,
            "runs_running": 0,
        }

    @app.get("/api/watchlist")
    def list_watchlist() -> list[dict]:
        return [queries.watchlist_to_dict(r) for r in queries.read_watchlist()]

    @app.get("/api/prices")
    def list_prices() -> dict:
        return app.state.price_state.snapshots

    @app.post("/api/watchlist", status_code=201)
    def add_to_watchlist(body: WatchlistIn) -> dict:
        from . import price_feed as _pf
        try:
            _pf.validate_ticker_exists(body.ticker)
        except _pf.TickerNotFound as exc:
            detail = {"error": "ticker_not_found", "ticker": body.ticker, "reason": exc.reason}
            raise HTTPException(status_code=400, detail=detail)
        try:
            row = queries.add_ticker(body.ticker, body.company_name, body.exchange)
        except queries.DuplicateTicker:
            raise HTTPException(status_code=409, detail="ticker already on watchlist")
        return queries.watchlist_to_dict(row)

    @app.delete("/api/watchlist/{ticker}", status_code=204)
    def remove_from_watchlist(ticker: str) -> Response:
        queries.remove_ticker(ticker)
        return Response(status_code=204)

    @app.patch("/api/watchlist/reorder")
    def reorder_watchlist(body: WatchlistReorderIn) -> list[dict]:
        queries.reorder_watchlist(body.tickers)
        return [queries.watchlist_to_dict(r) for r in queries.read_watchlist()]

    @app.patch("/api/watchlist/{ticker}")
    def update_watchlist_item(ticker: str, body: WatchlistUpdateIn) -> dict:
        row = queries.update_watchlist_item(ticker, group=body.group)
        if row is None:
            raise HTTPException(status_code=404, detail="ticker not found")
        return queries.watchlist_to_dict(row)

    @app.post("/api/runs", status_code=202)
    async def start_run(body: RunIn) -> dict:
        ticker = body.ticker.upper()
        if ticker not in {r["ticker"] for r in queries.read_watchlist()}:
            raise HTTPException(status_code=404, detail="ticker not on watchlist")
        date_str = storage.today_utc_iso()
        run_id = await runner.enqueue(
            ticker,
            date_str,
            force=bool(body.force),
            price_state=app.state.price_state,
        )
        return {"run_id": run_id}

    @app.get("/api/tickers/{ticker}/runs")
    def list_ticker_runs(ticker: str, limit: int = 50) -> list[dict]:
        rows = storage.list_ticker_runs(ticker.upper(), limit=limit)
        return [queries.run_to_dict(r) for r in rows]

    @app.get("/api/tickers/{ticker}/history")
    def get_ticker_history(ticker: str, range: str = "auto") -> dict:
        from . import history as _history
        status, body = _history.get_history(ticker, range)
        if status != 200:
            raise HTTPException(status_code=status, detail=body)
        return body

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        rj = storage.read_run(run_id)
        if rj is None:
            raise HTTPException(status_code=404, detail="run not found")
        out = queries.run_to_dict(rj)
        out["events"] = [queries.event_to_dict(e, run_id) for e in storage.list_run_events(run_id)]
        out["llm_calls"] = [queries.llm_call_to_dict(c) for c in storage.list_run_llm_calls(run_id)]
        out["stages"] = _load_stages(run_id)
        return out

    @app.get("/api/runs/{run_id}/trace")
    def get_run_trace(run_id: str, since: str = "", limit: int = 500, kind: str = "") -> dict:
        rj = storage.read_run(run_id)
        if rj is None:
            raise HTTPException(status_code=404, detail="run not found")
        kinds: set[str] | None = None
        if kind:
            kinds = {k.strip() for k in kind.split(",") if k.strip()}
            valid = {"event", "stage", "llm_call"}
            bad = kinds - valid
            if bad:
                raise HTTPException(status_code=400, detail=f"unknown kind(s): {sorted(bad)}; valid: {sorted(valid)}")
        limit = max(1, min(int(limit), 5000))
        return queries.build_trace(run_id, since=since, limit=limit, kinds=kinds)

    @app.get("/api/runs/{run_id}/health")
    def get_run_health(run_id: str) -> dict:
        result = queries.build_health(run_id)
        if not result.get("found"):
            raise HTTPException(status_code=404, detail="run not found")
        result["subscribers"] = len(events._subscribers.get(run_id, set()))
        return result

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict:
        rj = storage.read_run(run_id)
        if rj is None:
            raise HTTPException(status_code=404, detail="run not found")
        storage.mark_run_status(run_id, cancel_requested=True)
        return queries.run_to_dict(storage.read_run(run_id))

    @app.websocket("/ws/runs/{run_id}")
    async def ws_run(ws: WebSocket, run_id: str, since: Optional[str] = None) -> None:
        await ws.accept()
        _active_ws.add(ws)
        rj = storage.read_run(run_id)
        if rj is None:
            await ws.send_json({"type": "error", "detail": "run not found"})
            await ws.close()
            return
        for ev in storage.list_run_events(run_id):
            if since and (ev.get("id") or "") <= since:
                continue
            await ws.send_json(ev)
        events.subscribe(run_id, ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            events.unsubscribe(run_id, ws)
            _active_ws.discard(ws)

    @app.websocket("/ws/global")
    async def ws_global(ws: WebSocket) -> None:
        await ws.accept()
        _active_ws.add(ws)
        events.subscribe_global(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            events.unsubscribe_global(ws)
            _active_ws.discard(ws)

    # --- Background Past Runs ---
    from web.server import background_runs

    @app.post("/api/background-runs", status_code=201)
    def post_background_run(body: dict):
        try:
            job_id = background_runs.start(
                ticker=body["ticker"],
                date_from=body["date_from"],
                date_to=body["date_to"],
                every=body.get("every", "1d"),
                parallel=body.get("parallel", 1),
            )
        except (KeyError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        return {"job_id": job_id}

    @app.get("/api/background-runs")
    def get_background_runs():
        return {"jobs": background_runs.list_jobs(limit=50)}

    @app.get("/api/background-runs/{job_id}")
    def get_background_run(job_id: str):
        try:
            return background_runs.get(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None

    @app.post("/api/background-runs/{job_id}/cancel")
    def post_background_run_cancel(job_id: str):
        try:
            background_runs.cancel(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None
        return {"status": "ok"}

    @app.post("/api/background-runs/{job_id}/pause")
    def post_background_run_pause(job_id: str):
        try:
            background_runs.pause(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None
        return {"status": "ok"}

    @app.post("/api/background-runs/{job_id}/resume")
    def post_background_run_resume(job_id: str):
        try:
            background_runs.resume(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None
        return {"status": "ok"}

    # --- Config (read/write .env) ---
    _ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

    _CONFIG_KEYS = [
        "TRADINGAGENTS_LLM_PROVIDER",
        "TRADINGAGENTS_DEEP_THINK_LLM",
        "TRADINGAGENTS_QUICK_THINK_LLM",
        "TRADINGAGENTS_LLM_BACKEND_URL",
        "TRADINGAGENTS_OUTPUT_LANGUAGE",
        "TRADINGAGENTS_MAX_DEBATE_ROUNDS",
        "TRADINGAGENTS_MAX_RISK_ROUNDS",
        "TRADINGAGENTS_TEMPERATURE",
        "TRADINGAGENTS_BENCHMARK_TICKER",
        "TRADINGAGENTS_CHECKPOINT_ENABLED",
        "TRADINGAGENTS_LLM_CACHE_ENABLED",
    ]
    _API_KEY_ENVS = [
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "XAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_CN_API_KEY",
        "ZHIPU_API_KEY",
        "ZHIPU_CN_API_KEY",
        "MINIMAX_API_KEY",
        "MINIMAX_CN_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENAI_COMPATIBLE_API_KEY",
        "ALPHA_VANTAGE_API_KEY",
    ]

    def _read_dotenv() -> dict[str, str]:
        env_path = _ENV_PATH
        if not env_path.exists():
            return {}
        result: dict[str, str] = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, val = stripped.partition("=")
                result[key.strip()] = val.strip()
        return result

    def _write_dotenv(updates: dict[str, str]) -> dict[str, str]:
        env_path = _ENV_PATH
        existing = _read_dotenv()
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        seen: set[str] = set()
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _, _ = stripped.partition("=")
                key = key.strip()
                seen.add(key)
                if key in updates:
                    out.append(f"{key}={updates[key]}")
                else:
                    out.append(line)
            else:
                out.append(line)
        for key, val in updates.items():
            if key not in seen:
                out.append(f"{key}={val}")
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        for key, val in updates.items():
            os.environ[key] = val
        return _read_dotenv()

    @app.get("/api/config")
    def get_config():
        env = _read_dotenv()
        cfg = {}
        for key in _CONFIG_KEYS:
            cfg[key] = os.environ.get(key) or env.get(key, "")
        api_keys = {}
        for key in _API_KEY_ENVS:
            raw = os.environ.get(key) or env.get(key, "")
            api_keys[key] = bool(raw)
        return {"config": cfg, "api_keys": api_keys}

    @app.put("/api/config")
    def put_config(body: dict):
        updates = {}
        for key in _CONFIG_KEYS:
            if key in body:
                updates[key] = str(body[key])
        if "OPENAI_COMPATIBLE_API_KEY" in body:
            updates["OPENAI_COMPATIBLE_API_KEY"] = str(body["OPENAI_COMPATIBLE_API_KEY"])
        if not updates:
            raise HTTPException(status_code=400, detail="no recognised config keys")
        _write_dotenv(updates)
        cfg = {}
        env = _read_dotenv()
        for key in _CONFIG_KEYS:
            cfg[key] = os.environ.get(key) or env.get(key, "")
        return {"config": cfg, "status": "saved"}

    # ── Free LLM Keys Fetcher ─────────────────────────────────────

    @app.post("/api/free-llm-keys/fetch")
    async def fetch_free_llm_keys():
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(_FREE_KEYS_README_URL)
                resp.raise_for_status()
                text = resp.text
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch keys list: {e}")

        entries = _parse_free_key_tables(text)

        async def event_stream():
            if not entries:
                yield f"event: done\ndata: {json.dumps({'keys': [], 'base_url': _FREE_KEYS_API_BASE})}\n\n"
                return

            yield f"event: meta\ndata: {json.dumps({'total': len(entries), 'base_url': _FREE_KEYS_API_BASE})}\n\n"

            results: list[dict] = []
            sem = asyncio.Semaphore(10)

            async def _test_and_mask(entry: dict) -> dict:
                async with sem:
                    r = await _test_one_key(entry, _FREE_KEYS_API_BASE)
                k = r["key"]
                r["masked_key"] = f"{k[:10]}...{k[-4:]}" if len(k) > 14 else k
                return r

            tasks = [_test_and_mask(e) for e in entries]
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                yield f"event: key_result\ndata: {json.dumps(result)}\n\n"
                yield f"event: progress\ndata: {json.dumps({'tested': len(results), 'total': len(entries)})}\n\n"

            status_rank = {"working": 0, "low_balance": 1, "rate_limited": 2, "no_access": 3, "error": 4, "unknown": 5}
            results.sort(key=lambda r: (status_rank.get(r["status"], 99), r["provider"], r["model"]))
            yield f"event: done\ndata: {json.dumps({'keys': results, 'base_url': _FREE_KEYS_API_BASE})}\n\n"

            _cache_free_keys(results)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/api/free-llm-keys/refresh-cache")
    async def refresh_free_keys_cache():
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(_FREE_KEYS_README_URL)
                resp.raise_for_status()
                text = resp.text
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch keys list: {e}")

        entries = _parse_free_key_tables(text)
        results: list[dict] = []
        if entries:
            sem = asyncio.Semaphore(10)

            async def _test_and_mask(entry: dict) -> dict:
                async with sem:
                    r = await _test_one_key(entry, _FREE_KEYS_API_BASE)
                k = r["key"]
                r["masked_key"] = f"{k[:10]}...{k[-4:]}" if len(k) > 14 else k
                return r

            tasks = [_test_and_mask(e) for e in entries]
            for coro in asyncio.as_completed(tasks):
                results.append(await coro)

            status_rank = {"working": 0, "low_balance": 1, "rate_limited": 2, "no_access": 3, "error": 4, "unknown": 5}
            results.sort(key=lambda r: (status_rank.get(r["status"], 99), r["provider"], r["model"]))

        _cache_free_keys(results)
        return {"status": "ok", "count": len(results)}

    @app.get("/api/free-llm-keys/cached")
    def get_cached_free_llm_keys():
        cache_path = storage.data_dir() / "free_llm_keys_cache.json"
        data = storage.read_json(cache_path)
        if data is None:
            raise HTTPException(status_code=404, detail="no cached keys")
        return data

    # static mount (only if build dir exists)
    settings = settings_mod.get_settings()
    if os.path.isdir(settings.frontend_dist):
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app


def _load_stages(run_id: str) -> list[dict]:
    rd = storage.read_run_dir(run_id)
    if rd is None:
        return []
    out = []
    for sp in sorted((rd / "stages").glob("*.json")):
        d = storage.read_json(sp) or {}
        out.append(d)
    return out