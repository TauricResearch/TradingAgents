"""FastAPI SSE backend for the structured equity ranking engine."""

import os
import time
import uuid
import asyncio
import json
import traceback as _tb
from datetime import date

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# If using Groq (or other OpenAI-compatible), set OPENAI_API_KEY for langchain
if not os.environ.get("OPENAI_API_KEY"):
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        os.environ["OPENAI_API_KEY"] = groq_key

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

app = FastAPI(title="TradingAgents Structured Pipeline")

# --- CORS ---
_cors_env = os.getenv("CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Auth ---
_API_KEY = os.getenv("AGENTS_API_KEY", "")


async def verify_api_key(request: Request):
    if not _API_KEY:
        return
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {_API_KEY}":
        raise HTTPException(401, "Invalid or missing API key")


# --- Concurrency ---
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_ANALYSES", "3"))
_semaphore = asyncio.Semaphore(MAX_CONCURRENT)

analyses: dict[str, dict] = {}


class AnalyzeRequest(BaseModel):
    ticker: str
    date: str | None = None


def build_config():
    """Build TradingAgents config from env vars."""
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = os.getenv("LLM_PROVIDER", "openai")
    config["deep_think_llm"] = os.getenv("DEEP_THINK_MODEL", "deepseek-v3.1:671b-cloud")
    config["quick_think_llm"] = os.getenv("QUICK_THINK_MODEL", "deepseek-v3.1:671b-cloud")
    config["backend_url"] = os.getenv("LLM_BASE_URL", "https://ollama.com/v1")
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }
    print(
        f"[CONFIG] provider={config['llm_provider']}, "
        f"deep={config['deep_think_llm']}, "
        f"quick={config['quick_think_llm']}, "
        f"url={config['backend_url']}",
        flush=True,
    )
    return config


# ---------------------------------------------------------------------------
# Stage/agent mapping for SSE events
# ---------------------------------------------------------------------------

# Maps state field → (agent display name, pipeline stage)
FIELD_AGENT_MAP = {
    "validation": ("Validation", "validation"),
    "company_card": ("Company Card", "validation"),
    "macro": ("Macro Regime", "tier1"),
    "liquidity": ("Liquidity", "tier1"),
    "business_quality": ("Business Quality", "tier2"),
    "institutional_flow": ("Institutional Flow", "tier2"),
    "valuation": ("Valuation", "tier2"),
    "entry_timing": ("Entry Timing", "tier2"),
    "earnings_revisions": ("Earnings Revisions", "tier2"),
    "sector_rotation": ("Sector Rotation", "tier2"),
    "backlog": ("Backlog / Order Momentum", "tier2"),
    "crowding": ("Narrative Crowding", "tier2"),
    "archetype": ("Archetype", "scoring"),
    "master_score": ("Master Score", "scoring"),
    "bull_case": ("Bull Researcher", "debate"),
    "bear_case": ("Bear Researcher", "debate"),
    "debate": ("Debate Referee", "debate"),
    "risk": ("Risk / Invalidation", "decision"),
    "final_decision": ("Final Decision", "decision"),
}

ALL_AGENTS = [name for name, _ in FIELD_AGENT_MAP.values()]
ALL_STAGES = ["validation", "tier1", "tier2", "scoring", "debate", "decision"]


# ---------------------------------------------------------------------------
# Analysis runner
# ---------------------------------------------------------------------------

async def _run_analysis_inner(analysis_id: str, ticker: str, trade_date: str):
    """Core analysis logic — streams structured pipeline state changes as SSE."""
    state = analyses[analysis_id]
    q = state["queue"]
    config = build_config()

    try:
        graph = TradingAgentsGraph(debug=False, config=config)
        print(
            f"[ANALYSIS] LLM types: deep={type(graph.deep_thinking_llm).__name__}, "
            f"quick={type(graph.quick_thinking_llm).__name__}",
            flush=True,
        )
    except Exception as e:
        print(f"[ANALYSIS] Init failed: {e}\n{_tb.format_exc()}", flush=True)
        await q.put({"type": "error", "message": f"Init failed: {e}"})
        await q.put(None)
        return

    init_state = graph._create_initial_state(ticker, trade_date)
    start_time = time.time()
    emitted_fields = set()
    prev_agent_statuses = {}
    final_state = None

    # Emit initial status: all agents pending
    for field, (agent_name, stage) in FIELD_AGENT_MAP.items():
        prev_agent_statuses[field] = "pending"
        evt = {
            "type": "agent_update",
            "agent": agent_name,
            "stage": stage,
            "status": "pending",
            "stats": _stats(start_time, emitted_fields),
        }
        state["events"].append(evt)
        await q.put(evt)

    try:
        async for chunk in graph.graph.astream(
            init_state,
            stream_mode="values",
            config={"recursion_limit": 50},
        ):
            final_state = chunk

            # Detect newly populated fields
            for field, (agent_name, stage) in FIELD_AGENT_MAP.items():
                if field in emitted_fields:
                    continue

                value = chunk.get(field)
                if value is None:
                    continue

                emitted_fields.add(field)
                st = _stats(start_time, emitted_fields)

                # Mark this agent completed
                prev_agent_statuses[field] = "completed"
                evt = {
                    "type": "agent_update",
                    "agent": agent_name,
                    "stage": stage,
                    "status": "completed",
                    "stats": st,
                }
                state["events"].append(evt)
                await q.put(evt)

                # Emit report data for key fields
                if field in ("validation", "company_card"):
                    evt = {
                        "type": "report",
                        "agent": agent_name,
                        "stage": stage,
                        "field": field,
                        "report": _format_report(field, value),
                        "stats": st,
                    }
                    state["events"].append(evt)
                    await q.put(evt)

                elif field == "debate":
                    bull = chunk.get("bull_case") or {}
                    bear = chunk.get("bear_case") or {}
                    evt = {
                        "type": "debate",
                        "stage": "debate",
                        "bull": bull.get("thesis", ""),
                        "bear": bear.get("thesis", ""),
                        "judge": (value or {}).get("reasoning", ""),
                        "winner": (value or {}).get("winner", ""),
                        "stats": st,
                    }
                    state["events"].append(evt)
                    await q.put(evt)

                elif field == "master_score":
                    evt = {
                        "type": "score",
                        "stage": "scoring",
                        "master_score": value,
                        "adjusted_score": chunk.get("adjusted_score"),
                        "position_role": chunk.get("position_role"),
                        "stats": st,
                    }
                    state["events"].append(evt)
                    await q.put(evt)

            # Mark in-progress agents for upcoming stages
            _update_in_progress(chunk, emitted_fields, prev_agent_statuses, state, q, start_time)

    except Exception as e:
        print(f"[ANALYSIS] Stream error: {e}\n{_tb.format_exc()}", flush=True)
        evt = {"type": "error", "message": str(e)}
        state["events"].append(evt)
        await q.put(evt)
        state["done"] = True
        await q.put(None)
        return

    # Final decision event
    if final_state:
        decision = final_state.get("final_decision") or {}
        st = _stats(start_time, emitted_fields)

        # Mark all remaining as completed
        for field in FIELD_AGENT_MAP:
            if prev_agent_statuses.get(field) != "completed":
                agent_name, stage = FIELD_AGENT_MAP[field]
                prev_agent_statuses[field] = "completed"
                evt = {
                    "type": "agent_update",
                    "agent": agent_name,
                    "stage": stage,
                    "status": "completed",
                    "stats": st,
                }
                state["events"].append(evt)
                await q.put(evt)

        evt = {
            "type": "decision",
            "stage": "decision",
            "signal": decision.get("action", "AVOID"),
            "decision_text": decision.get("narrative", ""),
            "master_score": final_state.get("master_score"),
            "adjusted_score": final_state.get("adjusted_score"),
            "position_role": final_state.get("position_role"),
            "final_decision": decision,
            "stats": st,
        }
        state["events"].append(evt)
        await q.put(evt)

    state["done"] = True
    await q.put(None)


async def _update_in_progress(chunk, emitted, statuses, state, q, start_time):
    """Heuristic: mark agents as in_progress based on stage progression."""
    # If validation is done, mark tier 1 as in_progress
    if "validation" in emitted:
        for field in ("macro", "liquidity"):
            if field not in emitted and statuses.get(field) == "pending":
                statuses[field] = "in_progress"
                agent_name, stage = FIELD_AGENT_MAP[field]
                evt = {
                    "type": "agent_update",
                    "agent": agent_name,
                    "stage": stage,
                    "status": "in_progress",
                    "stats": _stats(start_time, emitted),
                }
                state["events"].append(evt)
                await q.put(evt)

    # If tier 1 done, mark tier 2 in_progress
    if "macro" in emitted and "liquidity" in emitted:
        tier2_fields = [
            "business_quality", "institutional_flow", "valuation",
            "entry_timing", "earnings_revisions", "sector_rotation",
            "backlog", "crowding",
        ]
        for field in tier2_fields:
            if field not in emitted and statuses.get(field) == "pending":
                statuses[field] = "in_progress"
                agent_name, stage = FIELD_AGENT_MAP[field]
                evt = {
                    "type": "agent_update",
                    "agent": agent_name,
                    "stage": stage,
                    "status": "in_progress",
                    "stats": _stats(start_time, emitted),
                }
                state["events"].append(evt)
                await q.put(evt)


def _stats(start_time: float, emitted_fields: set) -> dict:
    return {
        "agents_done": len(emitted_fields),
        "agents_total": len(FIELD_AGENT_MAP),
        "elapsed": round(time.time() - start_time, 1),
    }


def _format_report(field: str, value) -> str:
    """Format a state field value as a readable report string."""
    if isinstance(value, dict):
        if "summary_1_sentence" in value:
            return value["summary_1_sentence"]
        if "company_name" in value:
            return f"{value.get('company_name', '')} ({value.get('ticker', '')}) — {value.get('sector', '')} / {value.get('industry', '')}"
        return json.dumps(value, indent=2, default=str)[:500]
    return str(value)[:500]


async def run_analysis(analysis_id: str, ticker: str, trade_date: str):
    """Background task with semaphore and timeout."""
    state = analyses[analysis_id]
    q = state["queue"]
    async with _semaphore:
        try:
            await asyncio.wait_for(
                _run_analysis_inner(analysis_id, ticker, trade_date),
                timeout=3600,
            )
        except asyncio.TimeoutError:
            print(f"[ANALYSIS] Timeout for {analysis_id}", flush=True)
            evt = {"type": "error", "message": "Analysis timed out after 60 minutes"}
            state["events"].append(evt)
            await q.put(evt)
            state["done"] = True
            await q.put(None)


# --- Cleanup ---
async def _cleanup_loop():
    while True:
        await asyncio.sleep(300)
        now = time.time()
        expired = [aid for aid, s in analyses.items() if now - s["created_at"] > 1800]
        for aid in expired:
            analyses.pop(aid, None)
        if expired:
            print(f"[CLEANUP] Removed {len(expired)} expired analyses", flush=True)


@app.on_event("startup")
async def _start_cleanup():
    asyncio.create_task(_cleanup_loop())


# --- Routes ---

@app.post("/analyze", dependencies=[Depends(verify_api_key)])
async def start_analysis(req: AnalyzeRequest):
    ticker = req.ticker.upper().strip()
    if not ticker or len(ticker) > 5 or not ticker.isalpha():
        raise HTTPException(400, "Invalid ticker")
    trade_date = req.date or str(date.today())
    analysis_id = str(uuid.uuid4())
    analyses[analysis_id] = {
        "queue": asyncio.Queue(),
        "events": [],
        "done": False,
        "created_at": time.time(),
    }
    asyncio.create_task(run_analysis(analysis_id, ticker, trade_date))
    return {"id": analysis_id, "ticker": ticker, "date": trade_date}


@app.get("/analyze/{analysis_id}/stream", dependencies=[Depends(verify_api_key)])
async def stream_analysis(analysis_id: str, last_event: int = 0):
    """Stream SSE events. Supports reconnection via ?last_event=N."""
    if analysis_id not in analyses:
        raise HTTPException(404, "Analysis not found")
    state = analyses[analysis_id]

    async def event_generator():
        idx = last_event
        while idx < len(state["events"]):
            evt = state["events"][idx]
            idx += 1
            yield {"id": str(idx), "data": json.dumps(evt)}
        if state["done"]:
            return
        q = state["queue"]
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=15)
            except asyncio.TimeoutError:
                yield {"event": "heartbeat", "data": ""}
                continue
            if event is None:
                break
            idx += 1
            yield {"id": str(idx), "data": json.dumps(event)}

    return EventSourceResponse(event_generator())


@app.get("/health")
async def health():
    return {"status": "ok", "engine": "structured_pipeline"}
