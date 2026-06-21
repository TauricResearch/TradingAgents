# Agent Observatory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified Agent Observatory panel providing full visibility into agent actions — thinking process, tool execution, agent communication, decision traceability, and ticker agent orchestration — while fixing 6+ bugs in the event emission layer.

**Architecture:** New `Observer` backend module enriches raw graph events with timing and full payloads, fixes broken event emissions (debate/risk messages, _NODE_STATE_KEY, EventType enum), and adds a WebSocket endpoint for the Ticker Agent. Frontend gets 6 new components (DAG, ThinkingStream, ToolTimeline, DebateFlow, DecisionTrace, TickerAgentPanel) housed in a toggleable Observatory panel.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Tailwind (frontend), WebSocket (real-time), LangGraph (agent framework)

## Global Constraints

- All new event types must be added to both `web/server/events.py` `EventType` enum and `web/frontend/src/lib/events.ts` simultaneously
- No truncation of agent thinking text or tool results in observatory events
- Ticker Agent WebSocket must gracefully fall back to polling if connection fails
- All existing tests must continue to pass

---

### Task 1: Fix Event Bugs in Backend

**Files:**
- Modify: `web/server/events.py:18-34`
- Modify: `web/server/runner.py:49-68, 159-172`
- Modify: `tradingagents/graph/trading_graph.py:20,45`
- Test: `web/server/tests/test_events.py`

**Interfaces:**
- Consumes: Current `EventType` enum, `_STAGE_MAP`, `_NODE_STATE_KEY`, duplicate imports
- Produces: Corrected `EventType` enum matching actual emissions, fixed `_NODE_STATE_KEY` with correct node names and state fields, deduplicated imports

- [ ] **Step 1: Write failing tests**

```python
# web/server/tests/test_events.py
from web.server.events import EventType

def test_event_type_values_match_emissions():
    """All EventType values must match what's actually emitted in callbacks.py and runner.py."""
    expected = {
        "run_started", "run_failed", "analyst_started", "analyst_thinking",
        "analyst_completed", "tool_call", "tool_result", "tool_call_warning",
        "run_finished", "decision", "debate_message", "risk_message",
        "price_update", "server_notice",
    }
    actual = {e.value for e in EventType}
    assert actual == expected, f"Missing: {expected - actual}, Extra: {actual - expected}"

def test_node_state_key_matches_graph_nodes():
    """_NODE_STATE_KEY keys must match actual LangGraph node names."""
    from web.server.runner import _NODE_STATE_KEY
    for node_name in _NODE_STATE_KEY:
        assert node_name in (
            "Market Analyst", "Sentiment Analyst", "News Analyst",
            "Fundamentals Analyst", "Bull Researcher", "Bear Researcher",
            "Research Manager", "Trader", "Aggressive Analyst",
            "Conservative Analyst", "Neutral Analyst", "Portfolio Manager",
        ), f"Unknown node: {node_name}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest web/server/tests/test_events.py -v`
Expected: FAIL — EventType mismatch, _NODE_STATE_KEY keys wrong

- [ ] **Step 3: Update EventType enum in events.py**

```python
class EventType(str, Enum):
    RUN_STARTED = "run_started"
    RUN_FAILED = "run_failed"
    RUN_FINISHED = "run_finished"
    ANALYST_STARTED = "analyst_started"
    ANALYST_THINKING = "analyst_thinking"
    ANALYST_COMPLETED = "analyst_completed"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_CALL_WARNING = "tool_call_warning"
    DEBATE_MESSAGE = "debate_message"
    RISK_MESSAGE = "risk_message"
    DECISION = "decision"
    PRICE_UPDATE = "price_update"
    SERVER_NOTICE = "server_notice"
```

Delete these dead members: `RUN_QUEUED`, `RUN_DONE`, `RUN_CANCELLED`, `ANALYST_MESSAGE`, `ANALYST_TOOL_CALL`, `ANALYST_TOOL_RESULT`, `STAGE_COMPLETED`, `LLM_CALL`, `TOKEN_USAGE`.

- [ ] **Step 4: Fix _NODE_STATE_KEY in runner.py**

```python
_NODE_STATE_KEY = {
    "Market Analyst": "market_report",
    "Sentiment Analyst": "sentiment_report",
    "News Analyst": "news_report",
    "Fundamentals Analyst": "fundamentals_report",
    "Bull Researcher": "investment_debate_state.bull_history",
    "Bear Researcher": "investment_debate_state.bear_history",
    "Research Manager": "investment_plan",
    "Trader": "trader_investment_plan",
    "Aggressive Analyst": "risk_debate_state.aggressive_history",
    "Conservative Analyst": "risk_debate_state.conservative_history",
    "Neutral Analyst": "risk_debate_state.neutral_history",
    "Portfolio Manager": "final_trade_decision",
}
```

- [ ] **Step 5: Remove duplicate import in trading_graph.py**

Delete line 20: `from tradingagents.llm_clients import create_llm_client`
Keep line 45: `from tradingagents.llm_clients import create_llm_client`

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest web/server/tests/test_events.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add web/server/events.py web/server/runner.py tradingagents/graph/trading_graph.py web/server/tests/test_events.py
git commit -m "fix: align EventType enum with actual emissions, fix _NODE_STATE_KEY, deduplicate import"
```

---

### Task 2: Emit Debate and Risk Messages from Graph Callbacks

**Files:**
- Modify: `web/server/runner.py:465-515`
- Test: `web/server/tests/test_runner.py`

**Interfaces:**
- Consumes: `event_callback("node_exited")` delta dict with `investment_debate_state` or `risk_debate_state`
- Produces: `debate_message` and `risk_message` events with `{side, text, round, timestamp}` payload

- [ ] **Step 1: Write failing tests**

```python
# web/server/tests/test_runner.py (add to existing test file)
import json
from pathlib import Path

def test_debate_message_emitted(tmp_path: Path, monkeypatch):
    """When a node_exited delta contains investment_debate_state, a debate_message event is emitted."""
    from web.server import events, storage
    from web.server.runner import _run_one
    events_captured = []

    def mock_emit(run_id, type_, data):
        events_captured.append((type_, data))

    monkeypatch.setattr(events, "emit", mock_emit)
    # ... setup mock run dir, run json, then invoke _run_one logic
    # verify any debate_message in events_captured
    assert any(t == "debate_message" for t, _ in events_captured)
```

- [ ] **Step 2: Add debate/risk emission in runner.py cb() handler**

In the `cb()` function in `runner.py`, after the existing `node_exited` handling, add:

```python
def cb(node_name: str, payload: dict) -> None:
    ...
    if node_name == "node_exited":
        delta = payload.get("delta", {})
        node = payload.get("node", "")
        ...
        # Emit debate_message for researcher debate
        debate_state = delta.get("investment_debate_state")
        if debate_state and isinstance(debate_state, dict):
            current = debate_state.get("current_response", "")
            if "Bull" in current:
                events.emit(run_id, "debate_message", {
                    "side": "Bull Researcher",
                    "text": current,
                    "turn": debate_state.get("count", 0) // 2 + 1,
                })
            elif "Bear" in current:
                events.emit(run_id, "debate_message", {
                    "side": "Bear Researcher",
                    "text": current,
                    "turn": debate_state.get("count", 0) // 2 + 1,
                })

        # Emit risk_message for risk debate
        risk_state = delta.get("risk_debate_state")
        if risk_state and isinstance(risk_state, dict):
            for side_key, side_label in [
                ("current_aggressive_response", "Aggressive Analyst"),
                ("current_conservative_response", "Conservative Analyst"),
                ("current_neutral_response", "Neutral Analyst"),
            ]:
                text = risk_state.get(side_key, "")
                if text:
                    events.emit(run_id, "risk_message", {
                        "side": side_label,
                        "text": text,
                        "turn": risk_state.get("count", 0) // 3 + 1,
                    })
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest web/server/tests/test_runner.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add web/server/runner.py web/server/tests/test_runner.py
git commit -m "feat: emit debate_message and risk_message from graph event callbacks"
```

---

### Task 3: Create Observer Backend Module

**Files:**
- Create: `web/server/observer.py`
- Test: `web/server/tests/test_observer.py`

**Interfaces:**
- Produces: `Observer` class with `enrich(event_type, payload) -> dict` that adds timing, full payloads, and correlation IDs

- [ ] **Step 1: Write tests for Observer enrichment**

```python
# web/server/tests/test_observer.py
from web.server.observer import Observer

def test_observer_enriches_tool_call_with_timing():
    obs = Observer()
    event = obs.enrich("tool_call", {"tool": "get_stock_data", "args": "AAPL"})
    assert "observer_ts" in event
    assert "observer_seq" in event

def test_observer_tracks_tool_duration():
    obs = Observer()
    start = obs.enrich("tool_call", {"tool": "get_stock_data"})
    end = obs.enrich("tool_result", {"tool": "get_stock_data", "summary": "..."})
    assert "duration_ms" in end["data"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest web/server/tests/test_observer.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Write Observer module**

```python
"""Observer: enriches raw events with timing, full payloads, and correlations."""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone


class Observer:
    """Enriches events with sequencing, timing, and cross-agent correlations.

    Usage:
        observer = Observer()
        enriched = observer.enrich("tool_call", {"tool": "get_stock_data", "args": "..."})
    """

    def __init__(self):
        self._seq = 0
        self._tool_starts: dict[str, float] = {}
        self._agent_starts: dict[str, float] = {}

    def enrich(self, event_type: str, data: dict) -> dict:
        self._seq += 1
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        enriched = {
            "observer_seq": self._seq,
            "observer_ts": now,
            "type": event_type,
            "data": dict(data),
        }

        # Tool timing
        if event_type == "tool_call":
            tool_name = data.get("tool", "unknown")
            self._tool_starts[tool_name] = time.monotonic()
        elif event_type == "tool_result":
            tool_name = data.get("tool", "unknown")
            start = self._tool_starts.pop(tool_name, None)
            if start is not None:
                enriched["data"]["duration_ms"] = int((time.monotonic() - start) * 1000)

        # Agent timing
        if event_type == "analyst_started":
            node = data.get("node", "unknown")
            self._agent_starts[node] = time.monotonic()
        elif event_type == "analyst_completed":
            node = data.get("node", "")
            start = self._agent_starts.pop(node, None)
            if start is not None:
                enriched["data"]["duration_ms"] = int((time.monotonic() - start) * 1000)

        return enriched
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest web/server/tests/test_observer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/server/observer.py web/server/tests/test_observer.py
git commit -m "feat: add Observer backend module for event enrichment"
```

---

### Task 4: Add WebSocket Endpoint for Ticker Agent

**Files:**
- Modify: `web/server/ticker_agent/orchestrator.py`
- Modify: `web/server/ticker_agent/router.py`
- Modify: `web/server/app.py`
- Test: `web/server/ticker_agent/tests/test_orchestrator_ws.py`

**Interfaces:**
- Produces: WS endpoint `/api/ticker-agent/ws` pushing `ticker_*` event types
- Consumes: `orchestrator.run_cycle()` emits events via shared WS subscribers dict

- [ ] **Step 1: Add WS subscriber management to orchestrator.py**

Add to `orchestrator.py`:
```python
import asyncio
from fastapi import WebSocket

_ws_subscribers: set[WebSocket] = set()

async def ws_broadcast(event: dict) -> None:
    """Broadcast event to all connected WS clients."""
    dead = set()
    for ws in _ws_subscribers:
        try:
            await ws.send_json(event)
        except Exception:
            dead.add(ws)
    _ws_subscribers -= dead

def ws_subscribe(ws: WebSocket) -> None:
    _ws_subscribers.add(ws)

def ws_unsubscribe(ws: WebSocket) -> None:
    _ws_subscribers.discard(ws)
```

Add `_emit_event()` function that writes to `_live_events` AND broadcasts via WS:
```python
def _emit_event(step: int, message: str, event_type: str = "ticker_step", detail: dict | None = None) -> None:
    global _event_id_counter
    with _lock:
        _event_id_counter += 1
        ev = {
            "id": _event_id_counter,
            "step": step,
            "step_name": STEP_NAMES[step] if 0 <= step < len(STEP_NAMES) else "Unknown",
            "message": message,
            "timestamp": _now_iso(),
            "event_type": event_type,
            "detail": detail or {},
        }
        _live_events.append(ev)
        if len(_live_events) > 200:
            _live_events[:50] = []
    # Schedule WS broadcast
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(ws_broadcast(ev))
    except RuntimeError:
        pass  # no running loop — just persist to in-memory
```

- [ ] **Step 2: Instrument run_cycle() with structured events**

Replace `_emit_live()` calls in `run_cycle()` with `_emit_event()` that carries structured detail:

```python
def run_cycle() -> dict:
    ...
    try:
        _emit_event(1, "Reading past conclusions from memory...", "ticker_step_started", {"step": 1})

        context = _gather_context()
        _emit_event(2, "Context gathered", "ticker_step_completed", {
            "step": 2, "universe_size": len(context.get("universe", [])),
            "watchlist_size": context.get("watchlist_size", 0),
            "scored_tickers": context.get("scored_tickers", 0),
            "coverage_gaps": len(context.get("coverage_gaps", [])),
        })

        prompt = _build_strategy_prompt(context)
        _emit_event(3, "Calling LLM for strategy plan...", "ticker_step_started", {"step": 3})
        llm_response = _call_llm_strategy(prompt)
        _emit_event(3, "Strategy plan received", "ticker_llm_call", {
            "prompt_preview": prompt[:500],
            "response": llm_response,
            "model": "gpt-4o-mini",
        })

        execution_result = _execute_plan(llm_response)
        _emit_event(4, "Execution complete", "ticker_step_completed", {
            "step": 4, "scheduled": execution_result.get("scheduled", [])
        })

        scores_result = _rank_and_store(context)
        _emit_event(5, "Ranking complete", "ticker_step_completed", {
            "step": 5, "scored": scores_result.get("scored", 0),
            "top_ticker": scores_result.get("top_ticker"),
        })

        _write_memory(context, llm_response, execution_result, scores_result)
        _emit_event(6, "Memory updated", "ticker_step_completed", {"step": 6})

        _self_improve(context)
        _emit_event(7, "Self-improvement complete", "ticker_step_completed", {"step": 7})

        ...
        _emit_event(0, "Cycle complete.", "ticker_cycle_completed", {
            "cycles_completed": _cycles_completed
        })
```

- [ ] **Step 3: Add WS endpoint to router.py**

```python
from fastapi import WebSocket, WebSocketDisconnect
from . import orchestrator

@router.websocket("/ws")
async def ticker_agent_ws(ws: WebSocket):
    await ws.accept()
    orchestrator.ws_subscribe(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive — client sends pings
    except WebSocketDisconnect:
        orchestrator.ws_unsubscribe(ws)
```

- [ ] **Step 4: Register WS endpoint in app.py**

Add to `register_routers()` or the app lifespan:
```python
from web.server.ticker_agent.router import router as ticker_agent_router
app.include_router(ticker_agent_router)
```
(If already registered, no change needed.)

- [ ] **Step 5: Run existing tests**

Run: `uv run pytest web/server/ticker_agent/tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/server/ticker_agent/orchestrator.py web/server/ticker_agent/router.py web/server/app.py
git commit -m "feat: add WebSocket endpoint for ticker agent with structured live events"
```

---

### Task 5: Create ObservatoryDag Frontend Component

**Files:**
- Create: `web/frontend/src/components/ObservatoryDag.tsx`
- Test: `web/frontend/src/__tests__/ObservatoryDag.test.tsx`

**Interfaces:**
- Consumes: `WsEvent[]` from the focused run's WebSocket stream
- Produces: Rendered DAG with node click handler `onNodeClick(nodeName: string)`

- [ ] **Step 1: Write failing test**

```tsx
// web/frontend/src/__tests__/ObservatoryDag.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { ObservatoryDag } from "../components/ObservatoryDag";

const mockEvents = [
  { id: "1", type: "analyst_started", ts: "2024-01-01T00:00:00Z", run_id: "r1", data: { node: "Market Analyst" } },
  { id: "2", type: "analyst_completed", ts: "2024-01-01T00:01:00Z", run_id: "r1", data: { node: "Market Analyst", stage: "market" } },
];

test("renders all agent nodes", () => {
  render(<ObservatoryDag events={mockEvents} onNodeClick={() => {}} />);
  expect(screen.getByText("Market Analyst")).toBeInTheDocument();
  expect(screen.getByText("Bull Researcher")).toBeInTheDocument();
  expect(screen.getByText("Portfolio Manager")).toBeInTheDocument();
});

test("shows correct status per agent", () => {
  render(<ObservatoryDag events={mockEvents} onNodeClick={() => {}} />);
  const market = screen.getByTestId("dag-node-Market Analyst");
  expect(market).toHaveClass("status-completed");
});

test("calls onNodeClick when a node is clicked", () => {
  const onClick = vi.fn();
  render(<ObservatoryDag events={mockEvents} onNodeClick={onClick} />);
  fireEvent.click(screen.getByTestId("dag-node-Market Analyst"));
  expect(onClick).toHaveBeenCalledWith("Market Analyst");
});
```

- [ ] **Step 2: Create ObservatoryDag component**

```tsx
// web/frontend/src/components/ObservatoryDag.tsx
import { useMemo } from "react";
import type { WsEvent } from "../lib/events";

interface DagNode {
  name: string;
  status: "pending" | "running" | "completed" | "errored";
  stage: string;
}

const AGENTS = [
  { name: "Market Analyst", stage: "market" },
  { name: "Sentiment Analyst", stage: "sentiment" },
  { name: "News Analyst", stage: "news" },
  { name: "Fundamentals Analyst", stage: "fundamentals" },
  { name: "Bull Researcher", stage: "research" },
  { name: "Bear Researcher", stage: "research" },
  { name: "Research Manager", stage: "research" },
  { name: "Trader", stage: "trader" },
  { name: "Aggressive Analyst", stage: "risk" },
  { name: "Conservative Analyst", stage: "risk" },
  { name: "Neutral Analyst", stage: "risk" },
  { name: "Portfolio Manager", stage: "risk" },
];

function statusForAgent(name: string, events: WsEvent[]): DagNode["status"] {
  const started = events.some(e => e.type === "analyst_started" && (e.data as any)?.node === name);
  const completed = events.some(e => e.type === "analyst_completed" && (e.data as any)?.node === name);
  const failed = events.some(e => e.type === "run_failed");
  if (completed) return "completed";
  if (started && !failed) return "running";
  if (failed && started) return "errored";
  return "pending";
}

const STATUS_STYLES: Record<DagNode["status"], { dot: string; bg: string; border: string }> = {
  completed: { dot: "bg-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/30" },
  running: { dot: "bg-sky-400 animate-pulse", bg: "bg-sky-500/10", border: "border-sky-400/30" },
  pending: { dot: "bg-slate-600", bg: "bg-slate-800/30", border: "border-slate-700/30" },
  errored: { dot: "bg-red-400", bg: "bg-red-500/10", border: "border-red-500/30" },
};

export function ObservatoryDag({ events, onNodeClick }: { events: WsEvent[]; onNodeClick: (name: string) => void }) {
  const nodes = useMemo(() => AGENTS.map(a => ({ ...a, status: statusForAgent(a.name, events) })), [events]);

  return (
    <div className="glass-panel p-3 space-y-3" data-testid="observatory-dag">
      <span className="section-header">Agent Flow</span>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
        {nodes.map(n => {
          const s = STATUS_STYLES[n.status];
          return (
            <button key={n.name} data-testid={`dag-node-${n.name}`}
              onClick={() => onNodeClick(n.name)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-left text-xs transition-all hover:brightness-125 ${s.bg} ${s.border}`}>
              <span className={`w-2 h-2 rounded-full shrink-0 ${s.dot}`} />
              <div className="min-w-0">
                <div className="text-slate-200 truncate font-medium">{n.name}</div>
                <div className="text-slate-500 capitalize text-[10px]">{n.status}</div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Run tests**

```bash
cd web/frontend && npx vitest run --reporter=verbose src/__tests__/ObservatoryDag.test.tsx
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/components/ObservatoryDag.tsx web/frontend/src/__tests__/ObservatoryDag.test.tsx
git commit -m "feat: add ObservatoryDag component for agent flow DAG visualization"
```

---

### Task 6: Create ThinkingStream Frontend Component

**Files:**
- Create: `web/frontend/src/components/ThinkingStream.tsx`
- Test: `web/frontend/src/__tests__/ThinkingStream.test.tsx`

- [ ] **Step 1: Create ThinkingStream component**

```tsx
// web/frontend/src/components/ThinkingStream.tsx
import { useRef, useEffect } from "react";
import type { WsEvent } from "../lib/events";

interface ThinkingStreamProps {
  events: WsEvent[];
  agentName: string;
}

export function ThinkingStream({ events, agentName }: ThinkingStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  const agentEvents = events.filter(e => {
    if (e.type !== "analyst_thinking") return false;
    return (e.data as any)?.node === agentName;
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentEvents.length]);

  if (agentEvents.length === 0) {
    return <div className="text-xs text-slate-600 italic py-4 text-center">No thinking data yet.</div>;
  }

  return (
    <div className="bg-slate-950/60 rounded-lg border border-slate-800/50 max-h-96 overflow-y-auto font-mono text-xs">
      {agentEvents.map((e, i) => {
        const d = e.data as any;
        const text = d.text_fragment || d.text_preview || "";
        const isPrompt = !!d.text_preview;
        return (
          <div key={i} className={`px-3 py-1.5 ${isPrompt ? "text-slate-500 bg-slate-900/40" : "text-slate-200"}`}>
            <span className="text-slate-600 mr-2">{new Date(e.ts).toLocaleTimeString()}</span>
            {text}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/frontend/src/components/ThinkingStream.tsx web/frontend/src/__tests__/ThinkingStream.test.tsx
git commit -m "feat: add ThinkingStream component for per-agent thinking viewer"
```

---

### Task 7: Create ToolTimeline Frontend Component

**Files:**
- Create: `web/frontend/src/components/ToolTimeline.tsx`
- Test: `web/frontend/src/__tests__/ToolTimeline.test.tsx`

- [ ] **Step 1: Create ToolTimeline component**

```tsx
// web/frontend/src/components/ToolTimeline.tsx
import { useState } from "react";
import type { WsEvent } from "../lib/events";

interface ToolTimelineProps {
  events: WsEvent[];
}

export function ToolTimeline({ events }: ToolTimelineProps) {
  const [expandedTool, setExpandedTool] = useState<string | null>(null);

  const toolEvents = events.filter(e => e.type === "tool_call" || e.type === "tool_result");

  if (toolEvents.length === 0) {
    return <div className="text-xs text-slate-600 italic py-4 text-center">No tool calls yet.</div>;
  }

  return (
    <div className="space-y-1">
      {toolEvents.map((e, i) => {
        const d = e.data as any;
        const isCall = e.type === "tool_call";
        const key = `${e.id}-${i}`;
        return (
          <div key={key}
            className={`flex items-center gap-2 px-3 py-1.5 rounded text-xs border-l-2 cursor-pointer hover:brightness-125 transition-all ${
              isCall ? "border-l-slate-600 bg-slate-800/20 text-slate-400" : "border-l-slate-500 bg-slate-800/10 text-slate-300"
            }`}
            onClick={() => setExpandedTool(expandedTool === key ? null : key)}>
            <span className="text-slate-600 font-mono w-12 shrink-0">{new Date(e.ts).toLocaleTimeString()}</span>
            <span className={`shrink-0 ${isCall ? "text-amber-400" : "text-emerald-400"}`}>
              {isCall ? "▶" : "✓"}
            </span>
            <span className="truncate">{d.tool || "unknown"} {isCall ? `(${String(d.args || "").slice(0, 60)})` : ""}</span>
            {!isCall && d.duration_ms != null && (
              <span className="text-slate-500 ml-auto shrink-0 font-mono">{d.duration_ms}ms</span>
            )}
            {expandedTool === key && (
              <div className="col-span-4 mt-1 bg-slate-950/60 rounded p-2 text-[11px] text-slate-400 whitespace-pre-wrap">
                {isCall ? `Args: ${JSON.stringify(d.args, null, 2)}` : `Result: ${String(d.summary || "")}`}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/frontend/src/components/ToolTimeline.tsx web/frontend/src/__tests__/ToolTimeline.test.tsx
git commit -m "feat: add ToolTimeline component for tool execution timeline"
```

---

### Task 8: Create DebateFlow Frontend Component

**Files:**
- Create: `web/frontend/src/components/DebateFlow.tsx`
- Test: `web/frontend/src/__tests__/DebateFlow.test.tsx`

- [ ] **Step 1: Create DebateFlow component**

```tsx
// web/frontend/src/components/DebateFlow.tsx
import { useRef, useEffect } from "react";
import type { WsEvent } from "../lib/events";

const SIDE_STYLES: Record<string, { bg: string; border: string; text: string; label: string }> = {
  "Bull Researcher": { bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-300", label: "🐂 Bull" },
  "Bear Researcher": { bg: "bg-red-500/10", border: "border-red-500/30", text: "text-red-300", label: "🐻 Bear" },
  "Aggressive Analyst": { bg: "bg-orange-500/10", border: "border-orange-500/30", text: "text-orange-300", label: "⚠️ Aggressive" },
  "Conservative Analyst": { bg: "bg-blue-500/10", border: "border-blue-500/30", text: "text-blue-300", label: "🛡️ Conservative" },
  "Neutral Analyst": { bg: "bg-slate-500/10", border: "border-slate-500/30", text: "text-slate-300", label: "⚖️ Neutral" },
};

interface DebateFlowProps {
  events: WsEvent[];
  type: "debate" | "risk";
}

export function DebateFlow({ events, type }: DebateFlowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  const msgType = type === "debate" ? "debate_message" : "risk_message";
  const messages = events.filter(e => e.type === msgType);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  if (messages.length === 0) {
    return <div className="text-xs text-slate-600 italic py-4 text-center">No {type} messages yet.</div>;
  }

  return (
    <div className="space-y-2 max-h-96 overflow-y-auto">
      {messages.map((e, i) => {
        const d = e.data as any;
        const side = d.side || "unknown";
        const style = SIDE_STYLES[side] || SIDE_STYLES["Neutral Analyst"];
        return (
          <div key={i} className={`flex ${side.startsWith("Bull") || side.startsWith("Aggressive") ? "justify-start" : "justify-end"}`}>
            <div className={`max-w-[80%] rounded-xl px-3 py-2 border ${style.bg} ${style.border}`}>
              <div className={`text-[10px] font-semibold mb-1 ${style.text}`}>
                {style.label} {d.turn ? `[Round ${d.turn}]` : ""}
              </div>
              <div className="text-xs text-slate-300 whitespace-pre-wrap">{d.text}</div>
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/frontend/src/components/DebateFlow.tsx web/frontend/src/__tests__/DebateFlow.test.tsx
git commit -m "feat: add DebateFlow component for chat-bubble debate viewer"
```

---

### Task 9: Create DecisionTrace Frontend Component

**Files:**
- Create: `web/frontend/src/components/DecisionTrace.tsx`
- Test: `web/frontend/src/__tests__/DecisionTrace.test.tsx`

- [ ] **Step 1: Create DecisionTrace component**

```tsx
// web/frontend/src/components/DecisionTrace.tsx
import { useState } from "react";
import type { WsEvent } from "../lib/events";

interface TraceNode {
  stage: string;
  label: string;
  icon: string;
  agent: string;
  summary: string;
  fullText: string | null;
}

const STAGE_CONFIG: Record<string, { label: string; icon: string }> = {
  market: { label: "Market Analysis", icon: "📊" },
  sentiment: { label: "Sentiment Analysis", icon: "💬" },
  news: { label: "News Analysis", icon: "📰" },
  fundamentals: { label: "Fundamentals", icon: "📈" },
  research: { label: "Research & Debate", icon: "🔬" },
  trader: { label: "Trader Proposal", icon: "💼" },
  risk: { label: "Risk Discussion", icon: "⚠️" },
};

export function DecisionTrace({ events }: { events: WsEvent[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const completedEvents = events.filter(e => e.type === "analyst_completed");
  const decisionEvent = events.find(e => e.type === "decision");

  const nodes: TraceNode[] = [];
  for (const e of completedEvents) {
    const d = e.data as any;
    const stage = d.stage as string;
    const config = STAGE_CONFIG[stage];
    if (!config) continue;
    nodes.push({
      stage,
      label: config.label,
      icon: config.icon,
      agent: d.node || stage,
      summary: (d.report_excerpt || d.report_text || "").slice(0, 120),
      fullText: d.report_text || null,
    });
  }

  if (nodes.length === 0 && !decisionEvent) {
    return <div className="text-xs text-slate-600 italic py-4 text-center">No decision data yet.</div>;
  }

  return (
    <div className="space-y-0">
      {nodes.map((n, i) => (
        <div key={n.stage}>
          <button
            onClick={() => setExpanded(expanded === n.stage ? null : n.stage)}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-slate-800/30 transition-colors border-l-2 border-slate-700 hover:border-sky-500">
            <span>{n.icon}</span>
            <div className="min-w-0 flex-1">
              <div className="text-slate-300 font-medium truncate">{n.agent}</div>
              <div className="text-slate-500 text-[10px] truncate">{n.summary}</div>
            </div>
            <span className="text-slate-600">{expanded === n.stage ? "▲" : "▼"}</span>
          </button>
          {expanded === n.stage && n.fullText && (
            <pre className="ml-6 mr-2 mb-2 p-3 bg-slate-950/60 rounded-lg text-xs text-slate-300 whitespace-pre-wrap font-mono border border-slate-800/50 max-h-64 overflow-y-auto">
              {n.fullText}
            </pre>
          )}
          {i < nodes.length - 1 && <div className="ml-3 w-px h-4 bg-slate-700/50 mx-auto" />}
        </div>
      ))}
      {decisionEvent && (
        <div className="mt-3 p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10">
          <div className="text-xs font-bold text-emerald-400">DECISION</div>
          <div className="text-sm font-bold text-emerald-300 mt-1">
            {(decisionEvent.data as any)?.action || "HOLD"}
            {(decisionEvent.data as any)?.target ? ` @ $${(decisionEvent.data as any).target}` : ""}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            Confidence: {((decisionEvent.data as any)?.confidence || 0) * 100}%
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/frontend/src/components/DecisionTrace.tsx web/frontend/src/__tests__/DecisionTrace.test.tsx
git commit -m "feat: add DecisionTrace component for decision provenance tree"
```

---

### Task 10: Create AgentObservatory Main Panel

**Files:**
- Create: `web/frontend/src/components/AgentObservatory.tsx`
- Modify: `web/frontend/src/App.tsx`

- [ ] **Step 1: Create AgentObservatory component**

```tsx
// web/frontend/src/components/AgentObservatory.tsx
import { useState } from "react";
import type { WsEvent } from "../lib/events";
import { ObservatoryDag } from "./ObservatoryDag";
import { ThinkingStream } from "./ThinkingStream";
import { ToolTimeline } from "./ToolTimeline";
import { DebateFlow } from "./DebateFlow";
import { DecisionTrace } from "./DecisionTrace";

type Tab = "dag" | "thinking" | "tools" | "debate" | "risk" | "decision";

interface AgentObservatoryProps {
  events: WsEvent[];
}

export function AgentObservatory({ events }: AgentObservatoryProps) {
  const [tab, setTab] = useState<Tab>("dag");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const tabs: { key: Tab; label: string }[] = [
    { key: "dag", label: "Flow" },
    { key: "thinking", label: "Thinking" },
    { key: "tools", label: "Tools" },
    { key: "debate", label: "Debate" },
    { key: "risk", label: "Risk" },
    { key: "decision", label: "Trace" },
  ];

  return (
    <div className="space-y-3" data-testid="agent-observatory">
      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b border-slate-700/50 pb-1">
        {tabs.map(t => (
          <button key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 text-xs rounded-t-lg transition-colors ${
              tab === t.key ? "bg-slate-800 text-sky-300 border-b-2 border-sky-400" : "text-slate-500 hover:text-slate-300"
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "dag" && (
        <ObservatoryDag events={events} onNodeClick={(name) => { setSelectedAgent(name); setTab("thinking"); }} />
      )}
      {tab === "thinking" && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-1">
            {["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst",
              "Bull Researcher", "Bear Researcher", "Research Manager", "Trader",
              "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager"].map(name => (
              <button key={name} onClick={() => setSelectedAgent(name)}
                className={`px-2 py-1 text-[10px] rounded-full border transition-colors ${
                  selectedAgent === name ? "bg-sky-500/20 border-sky-400/50 text-sky-300" : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-slate-200"
                }`}>
                {name}
              </button>
            ))}
          </div>
          {selectedAgent && <ThinkingStream events={events} agentName={selectedAgent} />}
        </div>
      )}
      {tab === "tools" && <ToolTimeline events={events} />}
      {tab === "debate" && <DebateFlow events={events} type="debate" />}
      {tab === "risk" && <DebateFlow events={events} type="risk" />}
      {tab === "decision" && <DecisionTrace events={events} />}
    </div>
  );
}
```

- [ ] **Step 2: Add observatory toggle to App.tsx**

In `App.tsx`, add a button/tab to toggle between the current main content and the observatory view:

```tsx
// Near the top of App.tsx where other view toggles live
const [observatoryOpen, setObservatoryOpen] = useState(false);

// In the header/controls area
<button
  onClick={() => setObservatoryOpen(!observatoryOpen)}
  className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
    observatoryOpen ? "bg-sky-500/20 text-sky-300 border border-sky-500/30" : "bg-slate-800 text-slate-400 border border-slate-700/50 hover:text-slate-200"
  }`}>
  🔭 Observatory
</button>

// Conditionally render observatory or existing content
{observatoryOpen ? (
  <AgentObservatory events={focusedRunEvents} />
) : (
  // existing PipelineFlow / EventStream / DecisionPanel
)}
```

- [ ] **Step 3: Commit**

```bash
git add web/frontend/src/components/AgentObservatory.tsx web/frontend/src/App.tsx
git commit -m "feat: add AgentObservatory main panel with tabbed views"
```

---

### Task 11: Enhance TickerAgentDrawer with WebSocket + LLM Viewer + Step Detail

**Files:**
- Modify: `web/frontend/src/components/TickerAgentDrawer.tsx`
- Modify: `web/frontend/src/lib/api.ts`

- [ ] **Step 1: Add WebSocket connection hook for ticker agent**

In `api.ts`, add:
```typescript
// Ticker Agent WebSocket
export function connectTickerAgentWs(
  onEvent: (event: AgentLiveEvent) => void,
): () => void {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${protocol}//${window.location.host}/api/ticker-agent/ws`);
  ws.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data));
    } catch { /* ignore parse errors */ }
  };
  ws.onclose = () => {
    // Reconnect after 3s
    setTimeout(() => connectTickerAgentWs(onEvent), 3000);
  };
  return () => ws.close();
}
```

- [ ] **Step 2: Add WS-based event state to TickerAgentDrawer**

Add to `TickerAgentDrawer.tsx`:
```typescript
import { connectTickerAgentWs, type AgentLiveEvent } from "../lib/api";

// Inside component:
const [wsEvents, setWsEvents] = useState<AgentLiveEvent[]>([]);
const [wsConnected, setWsConnected] = useState(false);

useEffect(() => {
  const cleanup = connectTickerAgentWs((ev) => {
    setWsEvents(prev => [...prev.slice(-200), ev]);
    setWsConnected(true);
  });
  return cleanup;
}, []);
```

- [ ] **Step 3: Replace polling with WS data for live events**

Replace the polling-based `liveData` with `wsEvents`:
```typescript
const liveEvents = currentStatus === "running" ? wsEvents : [];
const currentStep = status?.current_step ?? 0;
```

- [ ] **Step 4: Add LLM Call Viewer section to the drawer**

Add after the Live Activity section:
```tsx
{/* LLM Strategy Call */}
{wsEvents.filter(e => e.event_type === "ticker_llm_call").length > 0 && (
  <div className="glass-panel p-3 space-y-2">
    <span className="section-header">LLM Strategy Call</span>
    {wsEvents.filter(e => e.event_type === "ticker_llm_call").map((ev, i) => (
      <details key={i} className="text-xs">
        <summary className="cursor-pointer text-sky-400 hover:text-sky-300">
          Strategy Call #{i + 1}
        </summary>
        <div className="mt-2 space-y-2">
          <div>
            <div className="text-slate-500 font-medium mb-1">Prompt:</div>
            <pre className="bg-slate-950/60 rounded p-2 text-slate-300 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto border border-slate-800/50">
              {ev.detail?.prompt_preview || "(no prompt)"}
            </pre>
          </div>
          <div>
            <div className="text-slate-500 font-medium mb-1">Response:</div>
            <pre className="bg-slate-950/60 rounded p-2 text-slate-300 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto border border-slate-800/50">
              {JSON.stringify(ev.detail?.response, null, 2) || "(no response)"}
            </pre>
          </div>
        </div>
      </details>
    ))}
  </div>
)}
```

- [ ] **Step 5: Add Step Detail section**

Add after the Step Progress section:
```tsx
{/* Step Details */}
{wsEvents.filter(e => e.event_type?.startsWith("ticker_step")).length > 0 && (
  <div className="glass-panel p-3 space-y-2">
    <span className="section-header">Step Details</span>
    <div className="space-y-1 max-h-48 overflow-y-auto">
      {wsEvents.filter(e => e.event_type?.startsWith("ticker_step"))
        .map((ev, i) => (
          <details key={i} className="text-xs border-b border-slate-800 last:border-0 py-1">
            <summary className="cursor-pointer text-slate-400 hover:text-slate-300">
              Step {ev.step}: {ev.step_name}
            </summary>
            <div className="mt-1 text-slate-500 space-y-0.5 pl-2">
              {ev.detail && Object.entries(ev.detail).map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <span className="text-slate-600 shrink-0">{k}:</span>
                  <span className="text-slate-400 truncate">{JSON.stringify(v)}</span>
                </div>
              ))}
            </div>
          </details>
        ))}
    </div>
  </div>
)}
```

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/components/TickerAgentDrawer.tsx web/frontend/src/lib/api.ts
git commit -m "feat: add WebSocket, LLM call viewer, and step details to TickerAgentDrawer"
```

---

### Task 12: Update Frontend Event Types to Match Backend

**Files:**
- Modify: `web/frontend/src/lib/events.ts`
- Modify: `web/frontend/src/__tests__/events-protocol.test.ts`

- [ ] **Step 1: Update events.ts with complete event type list**

```typescript
export const EventType = {
  RUN_STARTED: "run_started",
  RUN_FINISHED: "run_finished",
  RUN_FAILED: "run_failed",
  ANALYST_STARTED: "analyst_started",
  ANALYST_THINKING: "analyst_thinking",
  ANALYST_COMPLETED: "analyst_completed",
  TOOL_CALL: "tool_call",
  TOOL_RESULT: "tool_result",
  TOOL_CALL_WARNING: "tool_call_warning",
  DEBATE_MESSAGE: "debate_message",
  RISK_MESSAGE: "risk_message",
  DECISION: "decision",
  PRICE_UPDATE: "price_update",
  SERVER_NOTICE: "server_notice",
} as const;
```

- [ ] **Step 2: Update the protocol test to verify against actual Python enum**

```typescript
// events-protocol.test.ts
import { EventType } from "../lib/events";

const PYTHON_EVENT_TYPES = new Set([
  "run_started", "run_failed", "run_finished",
  "analyst_started", "analyst_thinking", "analyst_completed",
  "tool_call", "tool_result", "tool_call_warning",
  "debate_message", "risk_message",
  "decision", "price_update", "server_notice",
]);

test("frontend EventType matches backend EventType", () => {
  const frontendTypes = new Set(Object.values(EventType));
  expect(frontendTypes).toEqual(PYTHON_EVENT_TYPES);
});
```

- [ ] **Step 3: Run frontend tests**

```bash
cd web/frontend && npx vitest run --reporter=verbose
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/lib/events.ts web/frontend/src/__tests__/events-protocol.test.ts
git commit -m "fix: align frontend event types with backend, update protocol test"
```

---

### Task 13: Run Full Test Suite and Fix Regressions

- [ ] **Step 1: Run backend tests**

```bash
uv run pytest web/server/tests/ web/server/ticker_agent/tests/ -v
```
Expected: All PASS. If any fail, fix and re-run.

- [ ] **Step 2: Run frontend tests**

```bash
cd web/frontend && npx vitest run --reporter=verbose
```
Expected: All PASS. If any fail, fix and re-run.

- [ ] **Step 3: Run full backend test suite**

```bash
uv run pytest tests/ -v
```
Expected: All PASS (or pre-existing failures unrelated to changes).

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: test regressions from observatory changes"
```
