# TradingAgentsWeb Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a simple local FastAPI TradingAgentsWeb app that visually runs the existing TradingAgents CLI workflow.

**Architecture:** Add a thin root `web/` package that wraps existing CLI and graph behavior without duplicating TradingAgents core logic. Serve a plain HTML/CSS/JS one-page console and stream real graph execution events to the browser while enforcing one active run at a time.

**Tech Stack:** Python, FastAPI, Server-Sent Events, existing `TradingAgentsGraph`, plain HTML/CSS/JavaScript, pytest.

---

## File Structure

- Create `web/__init__.py`: package marker.
- Create `web/models.py`: Pydantic request and event models for the web API.
- Create `web/run_state.py`: one-active-run guard and in-memory run state.
- Create `web/config_builder.py`: converts form payloads into TradingAgents config and selected analysts.
- Create `web/streaming.py`: runs `TradingAgentsGraph` and yields browser events.
- Create `web/app.py`: FastAPI routes and static frontend serving.
- Create `web/static/index.html`: one-page run console.
- Create `web/static/styles.css`: app styling.
- Create `web/static/app.js`: frontend state and SSE handling.
- Modify `pyproject.toml`: add FastAPI/Uvicorn dependencies and web console script.
- Create `tests/web/test_config_builder.py`: validation and config tests.
- Create `tests/web/test_app_smoke.py`: import and route smoke tests.
- Update `docs/ARCHITECTURE.md`: keep implementation notes current if code decisions change.

## Task 1: Add Web Request Models

**Files:**
- Create: `web/__init__.py`
- Create: `web/models.py`
- Test: `tests/web/test_config_builder.py`

- [ ] **Step 1: Create package marker**

Create `web/__init__.py`:

```python
"""Web interface for TradingAgents."""
```

- [ ] **Step 2: Create request and event models**

Create `web/models.py`:

```python
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AnalysisRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    analysis_date: str
    output_language: str = "English"
    analysts: list[str] = Field(min_length=1)
    research_depth: int = Field(ge=1, le=5)
    llm_provider: str
    backend_url: str | None = None
    quick_think_llm: str
    deep_think_llm: str
    google_thinking_level: str | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    checkpoint_enabled: bool = False

    @field_validator("analysis_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        import datetime

        datetime.datetime.strptime(value, "%Y-%m-%d")
        return value

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class StreamEvent(BaseModel):
    type: Literal[
        "run_started",
        "agent_status",
        "message",
        "tool_call",
        "report_section",
        "stats",
        "run_completed",
        "run_failed",
    ]
    payload: dict[str, Any]
```

- [ ] **Step 3: Add model validation tests**

Create `tests/web/test_config_builder.py` with initial tests:

```python
import pytest
from pydantic import ValidationError

from web.models import AnalysisRequest


def test_analysis_request_normalizes_ticker():
    request = AnalysisRequest(
        ticker=" nvda ",
        analysis_date="2026-01-15",
        analysts=["market"],
        research_depth=1,
        llm_provider="openai",
        quick_think_llm="gpt-5.4-mini",
        deep_think_llm="gpt-5.4",
    )

    assert request.ticker == "NVDA"


def test_analysis_request_rejects_invalid_date():
    with pytest.raises(ValidationError):
        AnalysisRequest(
            ticker="NVDA",
            analysis_date="01-15-2026",
            analysts=["market"],
            research_depth=1,
            llm_provider="openai",
            quick_think_llm="gpt-5.4-mini",
            deep_think_llm="gpt-5.4",
        )
```

- [ ] **Step 4: Run tests and verify failure only if dependencies are missing**

Run: `pytest tests/web/test_config_builder.py -v`

Expected: tests pass once Pydantic imports are available.

## Task 2: Build Config Translation

**Files:**
- Create: `web/config_builder.py`
- Modify: `tests/web/test_config_builder.py`

- [ ] **Step 1: Add config builder**

Create `web/config_builder.py`:

```python
from cli.models import AnalystType
from cli.utils import detect_asset_type, filter_analysts_for_asset_type
from tradingagents.default_config import DEFAULT_CONFIG
from web.models import AnalysisRequest


ANALYST_ORDER = ["market", "social", "news", "fundamentals"]


def build_web_config(request: AnalysisRequest) -> tuple[dict, list[str], str]:
    asset_type = detect_asset_type(request.ticker)
    requested = [AnalystType(value) for value in request.analysts]
    allowed = filter_analysts_for_asset_type(requested, asset_type)
    selected = [analyst.value for analyst in allowed]

    if not selected:
        raise ValueError("At least one analyst must be selected for this asset type.")

    selected = [value for value in ANALYST_ORDER if value in set(selected)]

    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = request.research_depth
    config["max_risk_discuss_rounds"] = request.research_depth
    config["quick_think_llm"] = request.quick_think_llm
    config["deep_think_llm"] = request.deep_think_llm
    config["backend_url"] = request.backend_url
    config["llm_provider"] = request.llm_provider.lower()
    config["google_thinking_level"] = request.google_thinking_level
    config["openai_reasoning_effort"] = request.openai_reasoning_effort
    config["anthropic_effort"] = request.anthropic_effort
    config["output_language"] = request.output_language
    config["checkpoint_enabled"] = request.checkpoint_enabled

    return config, selected, asset_type.value
```

- [ ] **Step 2: Add config builder tests**

Append to `tests/web/test_config_builder.py`:

```python
from web.config_builder import build_web_config


def test_build_web_config_sets_core_values():
    request = AnalysisRequest(
        ticker="NVDA",
        analysis_date="2026-01-15",
        output_language="English",
        analysts=["market", "news"],
        research_depth=3,
        llm_provider="openai",
        backend_url="https://api.openai.com/v1",
        quick_think_llm="gpt-5.4-mini",
        deep_think_llm="gpt-5.4",
        openai_reasoning_effort="medium",
        checkpoint_enabled=True,
    )

    config, analysts, asset_type = build_web_config(request)

    assert config["max_debate_rounds"] == 3
    assert config["max_risk_discuss_rounds"] == 3
    assert config["llm_provider"] == "openai"
    assert config["checkpoint_enabled"] is True
    assert analysts == ["market", "news"]
    assert asset_type == "stock"


def test_build_web_config_removes_fundamentals_for_crypto():
    request = AnalysisRequest(
        ticker="BTC-USD",
        analysis_date="2026-01-15",
        analysts=["fundamentals", "market"],
        research_depth=1,
        llm_provider="openai",
        quick_think_llm="gpt-5.4-mini",
        deep_think_llm="gpt-5.4",
    )

    _, analysts, asset_type = build_web_config(request)

    assert analysts == ["market"]
    assert asset_type == "crypto"
```

- [ ] **Step 3: Run config tests**

Run: `pytest tests/web/test_config_builder.py -v`

Expected: all tests pass.

## Task 3: Add Run State Guard

**Files:**
- Create: `web/run_state.py`
- Test: `tests/web/test_app_smoke.py`

- [ ] **Step 1: Create run state guard**

Create `web/run_state.py`:

```python
from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4


@dataclass
class RunState:
    active_run_id: str | None = None
    lock: Lock = field(default_factory=Lock)

    def start(self) -> str:
        with self.lock:
            if self.active_run_id is not None:
                raise RuntimeError("Another analysis run is already active.")
            self.active_run_id = str(uuid4())
            return self.active_run_id

    def finish(self, run_id: str) -> None:
        with self.lock:
            if self.active_run_id == run_id:
                self.active_run_id = None


run_state = RunState()
```

- [ ] **Step 2: Add guard test**

Create `tests/web/test_app_smoke.py`:

```python
import pytest

from web.run_state import RunState


def test_run_state_allows_only_one_active_run():
    state = RunState()
    run_id = state.start()

    with pytest.raises(RuntimeError):
        state.start()

    state.finish(run_id)
    assert state.start()
```

- [ ] **Step 3: Run run-state test**

Run: `pytest tests/web/test_app_smoke.py -v`

Expected: test passes.

## Task 4: Add Streaming Runner

**Files:**
- Create: `web/streaming.py`

- [ ] **Step 1: Create SSE serialization and graph streaming**

Create `web/streaming.py`:

```python
import json
import time
from typing import Iterator

from cli.main import (
    ANALYST_AGENT_NAMES,
    ANALYST_ORDER,
    ANALYST_REPORT_MAP,
    classify_message_type,
)
from cli.stats_handler import StatsCallbackHandler
from tradingagents.graph.analyst_execution import (
    AnalystWallTimeTracker,
    build_analyst_execution_plan,
    get_initial_analyst_node,
    sync_analyst_tracker_from_chunk,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph
from web.config_builder import build_web_config
from web.models import AnalysisRequest, StreamEvent


def sse(event: StreamEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"


def _event(event_type: str, payload: dict) -> str:
    return sse(StreamEvent(type=event_type, payload=payload))


def stream_analysis(request: AnalysisRequest, run_id: str) -> Iterator[str]:
    config, selected_analysts, asset_type = build_web_config(request)
    stats_handler = StatsCallbackHandler()
    analyst_plan = build_analyst_execution_plan(
        selected_analysts,
        concurrency_limit=config["analyst_concurrency_limit"],
    )
    wall_time_tracker = AnalystWallTimeTracker(analyst_plan)
    graph = TradingAgentsGraph(
        selected_analysts,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )

    agent_status = {}
    for analyst in selected_analysts:
        agent_status[ANALYST_AGENT_NAMES[analyst]] = "pending"
    for agent in [
        "Bull Researcher",
        "Bear Researcher",
        "Research Manager",
        "Trader",
        "Aggressive Analyst",
        "Neutral Analyst",
        "Conservative Analyst",
        "Portfolio Manager",
    ]:
        agent_status[agent] = "pending"

    yield _event("run_started", {
        "run_id": run_id,
        "ticker": request.ticker,
        "analysis_date": request.analysis_date,
        "asset_type": asset_type,
        "agents": agent_status,
    })

    first = get_initial_analyst_node(analyst_plan)
    agent_status[first] = "in_progress"
    wall_time_tracker.mark_started(selected_analysts[0])
    yield _event("agent_status", {"agents": agent_status})

    init_state = graph.propagator.create_initial_state(
        request.ticker,
        request.analysis_date,
        asset_type=asset_type,
    )
    args = graph.propagator.get_graph_args(callbacks=[stats_handler])
    trace = []
    processed_message_ids = set()
    report_sections = {}
    start_time = time.time()

    for chunk in graph.graph.stream(init_state, **args):
        trace.append(chunk)

        for message in chunk.get("messages", []):
            msg_id = getattr(message, "id", None)
            if msg_id is not None:
                if msg_id in processed_message_ids:
                    continue
                processed_message_ids.add(msg_id)

            msg_type, content = classify_message_type(message)
            if content and content.strip():
                yield _event("message", {"message_type": msg_type, "content": content})

            if hasattr(message, "tool_calls") and message.tool_calls:
                for tool_call in message.tool_calls:
                    if isinstance(tool_call, dict):
                        name = tool_call["name"]
                        call_args = tool_call["args"]
                    else:
                        name = tool_call.name
                        call_args = tool_call.args
                    yield _event("tool_call", {"name": name, "args": call_args})

        sync_analyst_tracker_from_chunk(wall_time_tracker, chunk)
        active_found = False
        for analyst in ANALYST_ORDER:
            if analyst not in selected_analysts:
                continue
            agent_name = ANALYST_AGENT_NAMES[analyst]
            report_key = ANALYST_REPORT_MAP[analyst]
            if chunk.get(report_key):
                report_sections[report_key] = chunk[report_key]
                agent_status[agent_name] = "completed"
                yield _event("report_section", {"section": report_key, "content": chunk[report_key]})
            elif not report_sections.get(report_key) and not active_found:
                agent_status[agent_name] = "in_progress"
                active_found = True

        if not active_found and selected_analysts and agent_status.get("Bull Researcher") == "pending":
            agent_status["Bull Researcher"] = "in_progress"

        if chunk.get("investment_debate_state"):
            debate = chunk["investment_debate_state"]
            if debate.get("bull_history") or debate.get("bear_history"):
                agent_status["Bull Researcher"] = "in_progress"
                agent_status["Bear Researcher"] = "in_progress"
            if debate.get("judge_decision"):
                agent_status["Bull Researcher"] = "completed"
                agent_status["Bear Researcher"] = "completed"
                agent_status["Research Manager"] = "completed"
                agent_status["Trader"] = "in_progress"
            yield _event("report_section", {"section": "investment_debate_state", "content": debate})

        if chunk.get("trader_investment_plan"):
            agent_status["Trader"] = "completed"
            agent_status["Aggressive Analyst"] = "in_progress"
            yield _event("report_section", {"section": "trader_investment_plan", "content": chunk["trader_investment_plan"]})

        if chunk.get("risk_debate_state"):
            risk = chunk["risk_debate_state"]
            if risk.get("judge_decision"):
                agent_status["Aggressive Analyst"] = "completed"
                agent_status["Neutral Analyst"] = "completed"
                agent_status["Conservative Analyst"] = "completed"
                agent_status["Portfolio Manager"] = "completed"
            yield _event("report_section", {"section": "risk_debate_state", "content": risk})

        yield _event("agent_status", {"agents": agent_status})
        stats = stats_handler.get_stats()
        yield _event("stats", {"stats": stats, "elapsed_seconds": int(time.time() - start_time)})

    final_state = {}
    for chunk in trace:
        final_state.update(chunk)
    decision = graph.process_signal(final_state["final_trade_decision"])
    yield _event("run_completed", {"decision": decision, "final_state": final_state})
```

- [ ] **Step 2: Do not run real stream test without API keys**

Skip automated real-run tests for this task. This function executes real provider calls.

## Task 5: Add FastAPI App

**Files:**
- Create: `web/app.py`
- Modify: `pyproject.toml`
- Modify: `tests/web/test_app_smoke.py`

- [ ] **Step 1: Add FastAPI dependencies and script**

Modify `pyproject.toml` dependencies:

```toml
    "fastapi>=0.120.0",
    "uvicorn>=0.34.0",
```

Add script:

```toml
TradingAgentsWeb = "web.app:main"
```

- [ ] **Step 2: Create FastAPI app**

Create `web/app.py`:

```python
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.checkpointer import clear_all_checkpoints
from web.models import AnalysisRequest
from web.run_state import run_state
from web.streaming import stream_analysis


STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="TradingAgentsWeb")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/checkpoints/clear")
def clear_checkpoints():
    cleared = clear_all_checkpoints(DEFAULT_CONFIG["data_cache_dir"])
    return {"cleared": cleared}


@app.post("/api/analyze")
def analyze(request: AnalysisRequest):
    try:
        run_id = run_state.start()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    def generate():
        try:
            yield from stream_analysis(request, run_id)
        except Exception as exc:
            from web.models import StreamEvent
            yield f"data: {StreamEvent(type='run_failed', payload={'error': str(exc)}).model_dump_json()}\n\n"
        finally:
            run_state.finish(run_id)

    return StreamingResponse(generate(), media_type="text/event-stream")


def main():
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=True)
```

- [ ] **Step 3: Add app smoke test**

Append to `tests/web/test_app_smoke.py`:

```python
from fastapi.testclient import TestClient

from web.app import app


def test_index_loads():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
```

- [ ] **Step 4: Run smoke tests**

Run: `pytest tests/web/test_app_smoke.py -v`

Expected: tests pass.

## Task 6: Add Frontend Console

**Files:**
- Create: `web/static/index.html`
- Create: `web/static/styles.css`
- Create: `web/static/app.js`

- [ ] **Step 1: Create HTML shell**

Create `web/static/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>TradingAgentsWeb</title>
    <link rel="stylesheet" href="/static/styles.css">
  </head>
  <body>
    <main class="app-shell">
      <section class="setup-panel">
        <h1>TradingAgents</h1>
        <form id="analysis-form">
          <label>Ticker <input name="ticker" value="NVDA" required></label>
          <label>Analysis date <input name="analysis_date" type="date" required></label>
          <label>Output language <input name="output_language" value="English"></label>
          <fieldset>
            <legend>Analysts</legend>
            <label><input type="checkbox" name="analysts" value="market" checked> Market</label>
            <label><input type="checkbox" name="analysts" value="social" checked> Sentiment</label>
            <label><input type="checkbox" name="analysts" value="news" checked> News</label>
            <label><input type="checkbox" name="analysts" value="fundamentals" checked> Fundamentals</label>
          </fieldset>
          <label>Research depth
            <select name="research_depth">
              <option value="1">Shallow</option>
              <option value="3">Medium</option>
              <option value="5">Deep</option>
            </select>
          </label>
          <label>Provider <input name="llm_provider" value="openai"></label>
          <label>Backend URL <input name="backend_url" value="https://api.openai.com/v1"></label>
          <label>Quick model <input name="quick_think_llm" value="gpt-5.4-mini"></label>
          <label>Deep model <input name="deep_think_llm" value="gpt-5.4"></label>
          <label>OpenAI reasoning effort <input name="openai_reasoning_effort" value="medium"></label>
          <label><input type="checkbox" name="checkpoint_enabled"> Enable checkpoint resume</label>
          <div class="actions">
            <button type="submit">Run Analysis</button>
            <button type="button" id="clear-checkpoints">Clear Checkpoints</button>
          </div>
        </form>
      </section>
      <section class="dashboard">
        <div class="status-bar" id="status-bar">Idle</div>
        <div class="grid">
          <section class="panel"><h2>Agents</h2><div id="agents"></div></section>
          <section class="panel"><h2>Stats</h2><div id="stats"></div></section>
          <section class="panel report"><h2>Current Report</h2><pre id="report"></pre></section>
          <section class="panel"><h2>Messages</h2><div id="messages"></div></section>
        </div>
      </section>
    </main>
    <script src="/static/app.js"></script>
  </body>
</html>
```

- [ ] **Step 2: Create CSS**

Create `web/static/styles.css`:

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: Inter, Segoe UI, Arial, sans-serif; background: #f4f6f8; color: #17202a; }
.app-shell { display: grid; grid-template-columns: 360px 1fr; min-height: 100vh; }
.setup-panel { background: #ffffff; border-right: 1px solid #d8dee4; padding: 20px; overflow: auto; }
h1 { margin: 0 0 18px; font-size: 24px; }
h2 { margin: 0 0 12px; font-size: 15px; }
form { display: grid; gap: 12px; }
label, fieldset { display: grid; gap: 6px; font-size: 13px; }
fieldset { border: 1px solid #d8dee4; border-radius: 6px; padding: 10px; }
input, select, button { min-height: 36px; border: 1px solid #c8d0d9; border-radius: 6px; padding: 8px 10px; font: inherit; }
button { background: #1f6feb; color: #fff; border-color: #1f6feb; cursor: pointer; }
button[type="button"] { background: #ffffff; color: #1f2937; border-color: #c8d0d9; }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.dashboard { padding: 18px; overflow: auto; }
.status-bar { background: #111827; color: #fff; border-radius: 6px; padding: 12px 14px; margin-bottom: 14px; }
.grid { display: grid; grid-template-columns: 1fr 280px; grid-auto-rows: minmax(160px, auto); gap: 14px; }
.panel { background: #fff; border: 1px solid #d8dee4; border-radius: 8px; padding: 14px; overflow: auto; }
.report { min-height: 420px; }
pre { white-space: pre-wrap; margin: 0; font: 13px/1.5 Consolas, monospace; }
.agent { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #eef1f4; font-size: 13px; }
.message { border-bottom: 1px solid #eef1f4; padding: 8px 0; font-size: 13px; }
@media (max-width: 900px) {
  .app-shell { grid-template-columns: 1fr; }
  .setup-panel { border-right: 0; border-bottom: 1px solid #d8dee4; }
  .grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 3: Create JavaScript**

Create `web/static/app.js`:

```javascript
const form = document.querySelector("#analysis-form");
const statusBar = document.querySelector("#status-bar");
const agentsEl = document.querySelector("#agents");
const statsEl = document.querySelector("#stats");
const reportEl = document.querySelector("#report");
const messagesEl = document.querySelector("#messages");

function renderAgents(agents) {
  agentsEl.innerHTML = Object.entries(agents).map(([name, status]) =>
    `<div class="agent"><span>${name}</span><strong>${status}</strong></div>`
  ).join("");
}

function addMessage(type, text) {
  const node = document.createElement("div");
  node.className = "message";
  node.textContent = `${type}: ${text}`;
  messagesEl.prepend(node);
}

function payloadFromForm() {
  const data = new FormData(form);
  const analysts = data.getAll("analysts");
  return {
    ticker: data.get("ticker"),
    analysis_date: data.get("analysis_date"),
    output_language: data.get("output_language") || "English",
    analysts,
    research_depth: Number(data.get("research_depth")),
    llm_provider: data.get("llm_provider"),
    backend_url: data.get("backend_url") || null,
    quick_think_llm: data.get("quick_think_llm"),
    deep_think_llm: data.get("deep_think_llm"),
    openai_reasoning_effort: data.get("openai_reasoning_effort") || null,
    google_thinking_level: null,
    anthropic_effort: null,
    checkpoint_enabled: data.get("checkpoint_enabled") === "on"
  };
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusBar.textContent = "Starting analysis...";
  reportEl.textContent = "";
  messagesEl.innerHTML = "";

  const response = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payloadFromForm())
  });

  if (!response.ok || !response.body) {
    const error = await response.text();
    statusBar.textContent = `Error: ${error}`;
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      if (!part.startsWith("data: ")) continue;
      const event = JSON.parse(part.slice(6));
      handleEvent(event);
    }
  }
});

document.querySelector("#clear-checkpoints").addEventListener("click", async () => {
  const response = await fetch("/api/checkpoints/clear", { method: "POST" });
  const result = await response.json();
  statusBar.textContent = `Cleared ${result.cleared} checkpoint(s).`;
});

function handleEvent(event) {
  if (event.type === "run_started") {
    statusBar.textContent = `Running ${event.payload.ticker} for ${event.payload.analysis_date}`;
    renderAgents(event.payload.agents);
  } else if (event.type === "agent_status") {
    renderAgents(event.payload.agents);
  } else if (event.type === "message") {
    addMessage(event.payload.message_type, event.payload.content);
  } else if (event.type === "tool_call") {
    addMessage("Tool", `${event.payload.name} ${JSON.stringify(event.payload.args)}`);
  } else if (event.type === "report_section") {
    reportEl.textContent = typeof event.payload.content === "string"
      ? event.payload.content
      : JSON.stringify(event.payload.content, null, 2);
  } else if (event.type === "stats") {
    statsEl.textContent = JSON.stringify(event.payload, null, 2);
  } else if (event.type === "run_completed") {
    statusBar.textContent = `Completed: ${JSON.stringify(event.payload.decision)}`;
  } else if (event.type === "run_failed") {
    statusBar.textContent = `Failed: ${event.payload.error}`;
  }
}
```

## Task 7: Verify Locally

**Files:**
- Modify: `docs/ARCHITECTURE.md` only if implementation diverges from the design.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
pytest tests/web -v
```

Expected: all web tests pass.

- [ ] **Step 2: Start web server**

Run:

```powershell
python -m uvicorn web.app:app --host 127.0.0.1 --port 8000
```

Expected: server starts and serves `http://127.0.0.1:8000`.

- [ ] **Step 3: Manually verify page load**

Open `http://127.0.0.1:8000`.

Expected:

- Setup form appears on the left.
- Dashboard appears on the right.
- Clear checkpoints button returns a count.
- Starting a run without required provider credentials shows a visible failure instead of crashing the server.

- [ ] **Step 4: Keep architecture document current**

If the implementation changes any architectural decision, update `docs/ARCHITECTURE.md` in the same change.



