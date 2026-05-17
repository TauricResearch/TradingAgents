"""FastAPI application — settings endpoints, SSE analysis stream, static file serving."""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from web.settings import (
    DEFAULT_WEB_SETTINGS,
    build_run_config,
    load_settings,
    save_settings,
)
from web.settings import _SETTINGS_PATH as _DEFAULT_SETTINGS_PATH

SETTINGS_PATH = _DEFAULT_SETTINGS_PATH
_DIST = Path(__file__).parent / "frontend" / "dist"

app = FastAPI(title="TradingAgents Web UI")

# CORS for local Vite dev server — only when TRADINGAGENTS_WEB_DEV=1
if os.getenv("TRADINGAGENTS_WEB_DEV") == "1":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

_analysis_running: bool = False
_cancel_flag: threading.Event = threading.Event()
_executor = ThreadPoolExecutor(max_workers=1)


# ── Settings endpoints ─────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings() -> dict:
    return load_settings(SETTINGS_PATH)


@app.post("/api/settings")
async def post_settings(body: dict) -> dict:
    save_settings(body, SETTINGS_PATH)
    return body


# ── Stop endpoint ──────────────────────────────────────────────────────────

@app.post("/api/stop")
async def stop_analysis() -> dict:
    global _analysis_running
    _cancel_flag.set()
    _analysis_running = False
    return {"status": "stopped"}


# ── Analyze endpoint (SSE) ─────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze(body: dict) -> StreamingResponse:
    global _analysis_running
    if _analysis_running:
        raise HTTPException(status_code=409, detail="Analysis already running")

    ticker: str = body.get("ticker", "").strip().upper()
    date: str = body.get("date", "")
    if not ticker or not date:
        raise HTTPException(status_code=422, detail="ticker and date are required")

    web_config = load_settings(SETTINGS_PATH)
    run_config = build_run_config(web_config)
    analysts: list[str] = web_config.get("analysts", DEFAULT_WEB_SETTINGS["analysts"])

    _analysis_running = True
    _cancel_flag.clear()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    def _run() -> None:
        from cli.stats_handler import StatsCallbackHandler
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        _emitted_sections.clear()
        _analyst_reports.clear()

        try:
            stats = StatsCallbackHandler()
            graph = TradingAgentsGraph(
                analysts,
                config=run_config,
                debug=False,
                callbacks=[stats],
            )
            init_state = graph.propagator.create_initial_state(ticker, date)
            args = graph.propagator.get_graph_args(callbacks=[stats])

            start = time.time()
            trace: list[dict] = []

            for chunk in graph.graph.stream(init_state, **args):
                if _cancel_flag.is_set():
                    break
                events = _translate_chunk(chunk, analysts, stats, start)
                for ev in events:
                    loop.call_soon_threadsafe(queue.put_nowait, ev)
                trace.append(chunk)

            if trace and not _cancel_flag.is_set():
                final_state = trace[-1]
                decision = graph.process_signal(
                    final_state.get("final_trade_decision", "")
                )
                loop.call_soon_threadsafe(
                    queue.put_nowait, {"type": "complete", "decision": decision}
                )
        except Exception as exc:
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "error", "message": str(exc)}
            )
        finally:
            global _analysis_running
            _analysis_running = False
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(_executor, _run)

    async def _generator() -> AsyncGenerator[str, None]:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Chunk → SSE event translation ─────────────────────────────────────────

_ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
_ANALYST_NAMES = {
    "market": "Market Analyst",
    "social": "Social Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
_ANALYST_REPORT_KEYS = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}
_SECTION_TITLES = {
    "market_report": "Market Analysis",
    "sentiment_report": "Social Sentiment",
    "news_report": "News Analysis",
    "fundamentals_report": "Fundamentals Analysis",
    "investment_plan": "Research Team Decision",
    "trader_investment_plan": "Trading Team Plan",
    "final_trade_decision": "Portfolio Management Decision",
}

# Module-level tracking state — cleared at the start of each _run() call
_emitted_sections: set[str] = set()
_analyst_reports: dict[str, str] = {}


def _translate_chunk(
    chunk: dict,
    selected_analysts: list[str],
    stats_handler: Any,
    start_time: float,
) -> list[dict]:
    """Convert one graph stream chunk into a list of SSE event dicts."""
    events: list[dict] = []

    # ── Analyst statuses ──────────────────────────────────────────────────
    found_active = False
    for key in _ANALYST_ORDER:
        if key not in selected_analysts:
            continue
        report_key = _ANALYST_REPORT_KEYS[key]
        agent_name = _ANALYST_NAMES[key]
        if chunk.get(report_key):
            _analyst_reports[key] = chunk[report_key]
        has_report = bool(_analyst_reports.get(key))
        if has_report:
            if report_key not in _emitted_sections:
                events.append({
                    "type": "report_section",
                    "section": report_key,
                    "title": _SECTION_TITLES[report_key],
                    "content": _analyst_reports[key],
                })
                _emitted_sections.add(report_key)
            events.append({"type": "agent_status", "agent": agent_name, "status": "completed"})
        elif not found_active:
            events.append({"type": "agent_status", "agent": agent_name, "status": "in_progress"})
            found_active = True
        else:
            events.append({"type": "agent_status", "agent": agent_name, "status": "pending"})

    # When all selected analysts are done, start research team
    if not found_active and selected_analysts:
        events.append({"type": "agent_status", "agent": "Bull Researcher", "status": "in_progress"})

    # ── Research team ─────────────────────────────────────────────────────
    if chunk.get("investment_debate_state"):
        debate = chunk["investment_debate_state"]
        bull = (debate.get("bull_history") or "").strip()
        bear = (debate.get("bear_history") or "").strip()
        judge = (debate.get("judge_decision") or "").strip()
        if bull or bear:
            for agent in ("Bull Researcher", "Bear Researcher", "Research Manager"):
                events.append({"type": "agent_status", "agent": agent, "status": "in_progress"})
        content_parts = []
        if bull:
            content_parts.append(f"### Bull Researcher\n{bull}")
        if bear:
            content_parts.append(f"### Bear Researcher\n{bear}")
        if judge:
            content_parts.append(f"### Research Manager\n{judge}")
            for agent in ("Bull Researcher", "Bear Researcher", "Research Manager"):
                events.append({"type": "agent_status", "agent": agent, "status": "completed"})
            events.append({"type": "agent_status", "agent": "Trader", "status": "in_progress"})
        if content_parts and "investment_plan" not in _emitted_sections:
            events.append({
                "type": "report_section",
                "section": "investment_plan",
                "title": _SECTION_TITLES["investment_plan"],
                "content": "\n\n".join(content_parts),
            })
            if judge:
                _emitted_sections.add("investment_plan")

    # ── Trader ────────────────────────────────────────────────────────────
    if chunk.get("trader_investment_plan"):
        if "trader_investment_plan" not in _emitted_sections:
            events.append({
                "type": "report_section",
                "section": "trader_investment_plan",
                "title": _SECTION_TITLES["trader_investment_plan"],
                "content": chunk["trader_investment_plan"],
            })
            _emitted_sections.add("trader_investment_plan")
        events.append({"type": "agent_status", "agent": "Trader", "status": "completed"})
        events.append({"type": "agent_status", "agent": "Aggressive Analyst", "status": "in_progress"})

    # ── Risk management ───────────────────────────────────────────────────
    if chunk.get("risk_debate_state"):
        risk = chunk["risk_debate_state"]
        agg = (risk.get("aggressive_history") or "").strip()
        con = (risk.get("conservative_history") or "").strip()
        neu = (risk.get("neutral_history") or "").strip()
        judge = (risk.get("judge_decision") or "").strip()
        risk_parts = []
        if agg:
            risk_parts.append(f"### Aggressive Analyst\n{agg}")
            events.append({"type": "agent_status", "agent": "Aggressive Analyst", "status": "in_progress"})
        if con:
            risk_parts.append(f"### Conservative Analyst\n{con}")
            events.append({"type": "agent_status", "agent": "Conservative Analyst", "status": "in_progress"})
        if neu:
            risk_parts.append(f"### Neutral Analyst\n{neu}")
            events.append({"type": "agent_status", "agent": "Neutral Analyst", "status": "in_progress"})
        if judge:
            risk_parts.append(f"### Portfolio Manager\n{judge}")
            for agent in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager"):
                events.append({"type": "agent_status", "agent": agent, "status": "completed"})
        if risk_parts and "final_trade_decision" not in _emitted_sections:
            events.append({
                "type": "report_section",
                "section": "final_trade_decision",
                "title": _SECTION_TITLES["final_trade_decision"],
                "content": "\n\n".join(risk_parts),
            })
            if judge:
                _emitted_sections.add("final_trade_decision")

    # ── Stats ─────────────────────────────────────────────────────────────
    s = stats_handler.get_stats()
    events.append({
        "type": "stats",
        "llm_calls": s.get("llm_calls", 0),
        "tool_calls": s.get("tool_calls", 0),
        "tokens_in": s.get("tokens_in", 0),
        "tokens_out": s.get("tokens_out", 0),
        "elapsed_seconds": round(time.time() - start_time, 1),
    })

    return events


# ── Static file serving (production) ──────────────────────────────────────

if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/")
    async def serve_index() -> FileResponse:
        return FileResponse(str(_DIST / "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        file = _DIST / full_path
        if file.exists() and file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(_DIST / "index.html"))
