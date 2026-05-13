"""FastAPI web UI server for TradingAgents."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from pydantic import BaseModel

load_dotenv()

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS  # noqa: E402

class ProgressCallbackHandler(BaseCallbackHandler):
    """Pushes live tool/LLM activity events to the SSE queue."""

    def __init__(self, push_fn) -> None:
        super().__init__()
        self._push = push_fn
        self._lock = threading.Lock()
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    def on_chat_model_start(self, serialized, messages, **kwargs):
        with self._lock:
            self.llm_calls += 1
        name = (serialized.get("kwargs", {}).get("model") or
                serialized.get("kwargs", {}).get("model_name") or "LLM")
        self._push({"type": "progress", "event": "llm", "name": name})

    def on_llm_start(self, serialized, prompts, **kwargs):
        with self._lock:
            self.llm_calls += 1

    def on_llm_end(self, response: LLMResult, **kwargs):
        try:
            msg = response.generations[0][0].message
            usage = getattr(msg, "usage_metadata", None) or {}
            with self._lock:
                self.tokens_in  += usage.get("input_tokens", 0)
                self.tokens_out += usage.get("output_tokens", 0)
        except Exception:
            pass

    def on_tool_start(self, serialized, input_str, **kwargs):
        with self._lock:
            self.tool_calls += 1
        name = serialized.get("name", "tool")
        preview = (input_str or "")[:120]
        self._push({"type": "progress", "event": "tool", "name": name, "input": preview})

    def on_tool_end(self, output, **kwargs):
        preview = str(output or "")[:80]
        self._push({"type": "progress", "event": "tool_done", "preview": preview})

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "llm_calls": self.llm_calls,
                "tool_calls": self.tool_calls,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
            }


app = FastAPI(title="TradingAgents Web UI")

_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

# run_id → event queue (cleaned up after stream ends)
_runs: dict[str, Queue] = {}

_REPORT_FIELDS = {
    "market_report":        "Market Analyst",
    "sentiment_report":     "Social Analyst",
    "news_report":          "News Analyst",
    "fundamentals_report":  "Fundamentals Analyst",
    "investment_plan":      "Research Manager",
    "trader_investment_plan": "Trader",
    "final_trade_decision": "Portfolio Manager",
}


class AnalyzeRequest(BaseModel):
    # Field names mirror the frontend form in index.html
    ticker: str
    date: str
    analysts: list[str] = ["market", "social", "news", "fundamentals"]
    provider: str = "openai"
    quick_model: str = "gpt-5.4-mini"
    deep_model: str = "gpt-5.4-mini"
    max_debate_rounds: int = 1
    language: str = "English"
    checkpoint: bool = False


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))


@app.get("/api/models")
async def get_models():
    return MODEL_OPTIONS


@app.post("/api/analyze")
async def start_analysis(req: AnalyzeRequest) -> dict:
    run_id = str(uuid.uuid4())
    q: Queue = Queue()
    _runs[run_id] = q

    def _push(event: dict[str, Any]) -> None:
        q.put(event)

    def run() -> None:
        try:
            config = DEFAULT_CONFIG.copy()
            config["llm_provider"]          = req.provider
            config["quick_think_llm"]       = req.quick_model
            config["deep_think_llm"]        = req.deep_model
            config["max_debate_rounds"]     = req.max_debate_rounds
            config["max_risk_discuss_rounds"] = req.max_debate_rounds
            config["output_language"]       = req.language
            config["checkpoint_enabled"]    = req.checkpoint

            _push({"type": "status", "message": "Initializing…"})
            stats = ProgressCallbackHandler(_push)
            ta = TradingAgentsGraph(
                selected_analysts=req.analysts,
                debug=False,
                config=config,
                callbacks=[stats],
            )
            _push({"type": "status", "message": f"Analyzing {req.ticker} on {req.date}…"})

            prev: dict[str, str] = {}
            for chunk in ta.propagate_stream(req.ticker, req.date):
                for field, agent_name in _REPORT_FIELDS.items():
                    val = chunk.get(field) or ""
                    if val and val != prev.get(field, ""):
                        _push({"type": "report", "field": field, "agent": agent_name, "content": val})
                        prev[field] = val

            decision = ta.process_signal(
                (ta.curr_state or {}).get("final_trade_decision", "")
            )
            _push({
                "type": "complete",
                "decision": decision,
                "ticker": req.ticker,
                "date": req.date,
                "stats": stats.get_stats(),
            })

        except Exception as exc:
            _push({"type": "error", "message": str(exc)})
        finally:
            q.put(None)  # sentinel

    threading.Thread(target=run, daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/stream/{run_id}")
async def stream_job(run_id: str) -> StreamingResponse:
    q = _runs.get(run_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Run not found")

    async def _generate():
        loop = asyncio.get_event_loop()
        while True:
            try:
                item = await loop.run_in_executor(None, lambda: q.get(timeout=30))
            except Empty:
                yield ": keepalive\n\n"
                continue
            if item is None:
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                _runs.pop(run_id, None)
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
