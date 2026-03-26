# ADR 018 — Storage Layout, Event Persistence, WebSocket Streaming & Phase Re-run

**Status**: accepted
**Date**: 2026-03-26
**Supersedes**: ADR 015 (run_id namespacing — replaced by flow_id layout)
**Extends**: ADR 013 (WebSocket streaming — adds lazy-loading and run history)

---

## Context

This ADR finalises the storage architecture introduced across several PRs
(`feat/fe-max-tickers-load-run`, PR#106, PR#107, PR#108) and documents the
decisions made while fixing the Run History loading bug and phase-level re-run
capability.

Key problems solved:

1. **Run history lost on server restart** — in-memory run store (`runs` dict) is
   not durable. Users could not replay completed runs after a restart.
2. **Checkpoint-less re-runs** — re-running a node started from scratch (full
   analysts → debate → risk) instead of resuming from the correct phase.
3. **Re-run wiped full graph context** — clearing all events on re-run removed
   scan nodes and other tickers from the graph, leaving only the re-run phase.
4. **Analysts checkpoint never saved** — Social Analyst is optional; requiring
   *all* four analyst keys caused the checkpoint to be skipped silently.

---

## 1. Directory Structure (flow_id Layout)

### Layout

```
reports/
└── daily/
    └── {date}/                        ← e.g. 2026-03-26/
        ├── latest.json                ← pointer to most-recent flow_id (legacy compat)
        ├── daily_digest.md            ← appended by every run on this date
        ├── {flow_id}/                 ← 8-char hex, e.g. 021f29ef/
        │   ├── run_meta.json          ← run metadata (id, status, params, …)
        │   ├── run_events.jsonl       ← newline-delimited JSON events
        │   ├── market/
        │   │   └── report/
        │   │       ├── {ts}_scan_report.json
        │   │       └── {ts}_complete_report.json
        │   ├── {TICKER}/              ← e.g. RIG/, TSDD/
        │   │   └── report/
        │   │       ├── {ts}_complete_report.json
        │   │       ├── {ts}_analysts_checkpoint.json
        │   │       ├── {ts}_trader_checkpoint.json
        │   │       └── complete_report.md
        │   └── portfolio/
        │       └── report/
        │           ├── {ts}_pm_decision.json
        │           └── {ts}_execution_result.json
        └── runs/                      ← legacy run_id layout (backward compat only)
            └── {run_id}/
```

### flow_id vs run_id

| Concept | Type | Purpose |
|---------|------|---------|
| `run_id` | UUID | In-memory identity for a live run; used as WebSocket endpoint key |
| `flow_id` | 8-char hex timestamp | Disk storage key; stable across server restarts |

`flow_id` is generated once per run via `generate_flow_id()` and threaded through
all sub-phases of an auto run so scan + pipeline + portfolio share the same folder.
`run_id` is ephemeral — it exists only in the `runs` dict and is not persisted.

### Startup Hydration

On server start, `hydrate_runs_from_disk()` scans `reports/daily/*/` for
`run_meta.json` files and rebuilds the `runs` dict with `events: []` (lazy).
Events are only loaded when actually needed (WebSocket connect or GET run detail).

---

## 2. Event Structure

Every event sent over WebSocket or persisted to `run_events.jsonl` follows this
schema:

```jsonc
{
  // Core identity
  "type":           "thought" | "tool" | "tool_result" | "result" | "log" | "system",
  "node_id":        "Bull Researcher",          // LangGraph node name
  "parent_node_id": "Bull Researcher",          // parent node (for tool events)
  "identifier":     "RIG",                      // ticker, "MARKET", or portfolio_id
  "agent":          "BULL RESEARCHER",          // uppercase display name
  "timestamp":      "10:28:49",                 // HH:MM:SS

  // Content
  "message":        "Thinking... (gls...)",     // truncated display text
  "prompt":         "You are a bull researcher…", // full prompt (thought/result only)
  "response":       "Based on the analysis…",    // full response (result/tool_result)

  // Metrics (result events)
  "metrics": {
    "model":       "glm-4.7-flash:q4_K_M",
    "tokens_in":   1240,
    "tokens_out":  856,
    "latency_ms":  17843
  },

  // Tool events
  "status":  "running" | "success" | "error" | "graceful_skip",
  "service": "yfinance",                        // data vendor used

  // Re-run tracking
  "rerun_seq": 1                                // incremented on each phase re-run; 0 = original
}
```

### Event Types

| Type | Emitted by | Content |
|------|-----------|---------|
| `thought` | LLM streaming chunk | `message` (truncated), `prompt` |
| `result` | LLM final output | `message`, `prompt`, `response`, `metrics` |
| `tool` | Tool invocation start | `node_id`, `status: "running"`, `service` |
| `tool_result` | Tool completion | `status`, `response` (tool output), `service` |
| `log` | `RunLogger` | structured log line |
| `system` | Engine | human-readable status update; special messages `"Run completed."` and `"Error: …"` control frontend state machine |

### Graph Rendering Rules

The frontend renders graph nodes by grouping events on `(node_id, identifier)`.
For each unique pair, the node shows the **latest** event's metrics (last result
event wins). Nodes within the same `identifier` are stacked vertically; each
`identifier` becomes a column.

---

## 3. How Events Are Sent

### Normal Run Flow

```
POST /api/run/{type}              → queues run, returns run_id + flow_id
                                    status: "queued"
WS  /ws/stream/{run_id}           → connects
  if status == "queued"           → WebSocket IS the executor
    engine.run_*()                → streams events live to socket
    run_info["events"].append()   → events cached in memory
    run_info["status"] = completed/failed
  if status in running/completed/failed
    → replay cached events, poll for new ones until terminal state
```

### Background Task Flow (POST → BackgroundTask)

```
POST /api/run/{type}
  BackgroundTask(_run_and_store)  → drives engine generator
    events cached in runs[run_id]["events"]
    status updated to running → completed/failed
WS /ws/stream/{run_id}
  → enters "streaming from cache" loop
  → polls events[sent:] every 50ms until status is terminal
```

### Lazy-Loading (Server Restart / Run History)

```
Server restart
  hydrate_runs_from_disk()        → runs[run_id] = {..., "events": []}

WS /ws/stream/{run_id}
  run_info.events == []
    → create_report_store(flow_id=flow_id)
    → store.load_run_events(date)
    → run_info["events"] = disk_events
    if status == "running" and disk_events:
      → status = "failed", error = "Run did not complete (server restarted)"
  → replay all events, send "Run completed." or "Error: …"
```

### Key Invariants

- **Events are append-only** during a live run. Never modified in place.
- **run_events.jsonl is written on run completion** (not streamed to disk in real time).
  This is acceptable for V1; periodic flush is a future enhancement.
- **WebSocket polling interval** is 50ms (`_EVENT_POLL_INTERVAL_SECONDS = 0.05`).
- **System messages** `"Run completed."` and `"Error: <msg>"` are terminal — the
  frontend transitions to `completed` or `error` state on receiving them.

---

## 4. Checkpoint Structure

Checkpoints are intermediate snapshots that allow phase-level re-runs without
re-executing earlier phases.

### Analysts Checkpoint

**Written by**: `run_pipeline()` after the graph completes
**Condition**: at least one of `market_report`, `sentiment_report`,
`news_report`, `fundamentals_report` is populated (Social Analyst is optional)
**Path**: `{flow_id}/{TICKER}/report/{ts}_analysts_checkpoint.json`

```jsonc
{
  "company_of_interest": "RIG",
  "trade_date": "2026-03-26",
  "market_report": "…",          // from Market Analyst
  "news_report": "…",            // from News Analyst
  "fundamentals_report": "…",   // from Fundamentals Analyst
  "sentiment_report": "",        // from Social Analyst (may be empty — that's OK)
  "macro_regime_report": "…",   // from Macro Synthesis scan
  "messages": [...]             // LangGraph message history (for debate context)
}
```

**Used by**: `run_pipeline_from_phase()` when `phase == "debate_and_trader"`.
Overlaid onto `initial_state` before running `debate_graph`.

### Trader Checkpoint

**Written by**: `run_pipeline()` after the graph completes
**Condition**: `trader_investment_plan` is populated
**Path**: `{flow_id}/{TICKER}/report/{ts}_trader_checkpoint.json`

```jsonc
{
  "company_of_interest": "RIG",
  "trade_date": "2026-03-26",
  "market_report": "…",
  "news_report": "…",
  "fundamentals_report": "…",
  "sentiment_report": "",
  "macro_regime_report": "…",
  "investment_debate_state": {...},  // full bull/bear debate transcript
  "investment_plan": "…",            // Research Manager output
  "trader_investment_plan": "…",     // Trader output
  "messages": [...]
}
```

**Used by**: `run_pipeline_from_phase()` when `phase == "risk"`.

### Phase Re-run Routing

```
node_id              →  phase              →  checkpoint loaded
──────────────────────────────────────────────────────────────
Market Analyst       →  analysts           →  none (full re-run)
News Analyst         →  analysts           →  none
Fundamentals Analyst →  analysts           →  none
Social Analyst       →  analysts           →  none
Bull Researcher      →  debate_and_trader  →  analysts_checkpoint
Bear Researcher      →  debate_and_trader  →  analysts_checkpoint
Research Manager     →  debate_and_trader  →  analysts_checkpoint
Trader               →  debate_and_trader  →  analysts_checkpoint
Aggressive Analyst   →  risk               →  trader_checkpoint
Conservative Analyst →  risk               →  trader_checkpoint
Neutral Analyst      →  risk               →  trader_checkpoint
Portfolio Manager    →  risk               →  trader_checkpoint
```

After any phase re-run completes, the engine **cascades** to `run_portfolio()`
so the PM decision incorporates the updated ticker analysis.

### Checkpoint Lookup Rule

**CRITICAL**: The read store used to load checkpoints **must use the same
`flow_id` as the original run**. Without the `flow_id`, `_date_root()` falls
back to the legacy flat layout and will never find checkpoints stored under
`{flow_id}/{TICKER}/report/`.

In `trigger_rerun_node`, the original flow_id is resolved as:
```python
flow_id = run.get("flow_id") or run.get("short_rid") or run["params"].get("flow_id")
```
This is then passed through `rerun_params["flow_id"]` to `run_pipeline_from_phase`,
which passes it to `create_report_store(flow_id=flow_id)`.

---

## 5. Selective Event Filtering on Re-run

When a phase re-run is triggered, the run's event list is **selectively filtered**
to remove stale events for the re-run scope while preserving events from:
- Other tickers (TSDD events preserved when re-running RIG)
- Earlier phases of the same ticker (analyst events preserved when re-running debate)
- Scan/market events (always preserved)

```python
# Nodes cleared per phase (plus all tool events with matching parent_node_id)
debate_and_trader → {Bull Researcher, Bear Researcher, Research Manager, Trader,
                     Aggressive Analyst, Conservative Analyst, Neutral Analyst,
                     Portfolio Manager}
risk              → {Aggressive Analyst, Conservative Analyst, Neutral Analyst,
                     Portfolio Manager}
analysts          → all nodes for the ticker

# Portfolio cascade nodes (always cleared — re-run always cascades to PM)
{review_holdings, make_pm_decision}
```

The WebSocket replays this filtered set first (rebuilding the full graph), then
streams the new re-run events on top. The frontend's `clearEvents()` + WebSocket
reconnect ensures a clean state before replay.

---

## 6. MongoDB vs Local Storage — Decision Guide

### Use Local Storage (ReportStore) when:

- **Development or single-machine deployment** — no infrastructure required
- **Offline / air-gapped environments** — no network dependency
- **Report files are the primary output** — reports as .json/.md files that
  can be read with any tool
- **Simplicity over scalability** — one process, one machine

### Use MongoDB (MongoReportStore) when:

- **Multi-process or multi-node deployment** — local files are not shared
- **Run history across restarts** — hydration from MongoDB is more reliable
  than scanning the filesystem
- **Reflexion memory** — `ReflexionMemory` works best with MongoDB for
  efficient per-ticker history queries
- **Future: TTL / retention** — MongoDB TTL indexes make automatic cleanup easy
- **Production environments** — MongoDB provides durability, replication, and
  backup

### Configuration

```env
# Enable MongoDB:
TRADINGAGENTS_MONGO_URI=mongodb://localhost:27017
TRADINGAGENTS_MONGO_DB=tradingagents   # optional, default: "tradingagents"

# Local storage (default when MONGO_URI is unset):
TRADINGAGENTS_REPORTS_DIR=/path/to/reports   # optional, default: ./reports
```

### Factory Behaviour

```python
# Always use the factory — never instantiate stores directly
from tradingagents.portfolio.store_factory import create_report_store

# Writing: always pass flow_id (scopes writes to the correct run folder)
writer = create_report_store(flow_id=flow_id)

# Reading: omit flow_id (resolves via latest.json or MongoDB latest query)
reader = create_report_store()
```

`create_report_store()` returns:
1. `DualReportStore(MongoReportStore, ReportStore)` — when `MONGO_URI` is set
   and pymongo is installed (writes to both; reads from Mongo first, falls back
   to disk)
2. `ReportStore` — when MongoDB is unavailable or not configured

MongoDB failures **always** fall back to filesystem with a warning log. The
application must remain functional without MongoDB.

### Known V1 Limitations (Future Work)

| Issue | Status |
|-------|--------|
| `pymongo` is synchronous — blocks asyncio event loop | Deferred: migrate to `motor` before production |
| No TTL index — reports accumulate indefinitely | Deferred: requires retention policy decision |
| `MongoClient` created per store instance | Deferred: singleton via FastAPI app lifespan |
| `run_events.jsonl` written on completion, not streaming | Deferred: periodic flush for long runs |

---

## Consequences & Constraints

### MUST

- **Always use `create_report_store(flow_id=…)` for writes** — never pass no
  args when writing, as the flat fallback path will overwrite across runs.
- **Always pass the original `flow_id` when loading checkpoints for re-run** —
  checkpoint lookup will silently return `None` otherwise, causing full re-run
  fallback.
- **Save analysts checkpoint if `any()` analyst report is populated** — Social
  Analyst is optional; `all()` silently blocks checkpoints when social is disabled.
- **Selective event filtering on re-run** — never clear all events; always use
  `_filter_rerun_events(events, ticker, phase)` to preserve other tickers and
  earlier phases.

### MUST NOT

- **Never hard-code `ReportStore()` in engine methods** — always use the factory.
- **Never hold pymongo in the async hot path** — wrap in `asyncio.to_thread` if
  blocking becomes measurable.

### Source Files

```
tradingagents/portfolio/report_store.py       ← ReportStore (filesystem)
tradingagents/portfolio/mongo_report_store.py ← MongoReportStore
tradingagents/portfolio/dual_report_store.py  ← DualReportStore (both)
tradingagents/portfolio/store_factory.py      ← create_report_store()
tradingagents/report_paths.py                 ← flow_id/run_id helpers, ts_now()
agent_os/backend/main.py                      ← hydrate_runs_from_disk()
agent_os/backend/routes/runs.py               ← _run_and_store, _append_and_store,
                                                 _filter_rerun_events, trigger_rerun_node
agent_os/backend/routes/websocket.py          ← lazy-loading, orphaned run detection
agent_os/backend/services/langgraph_engine.py ← run_pipeline_from_phase, NODE_TO_PHASE,
                                                 checkpoint save/load logic
agent_os/frontend/src/hooks/useAgentStream.ts ← WebSocket client, event accumulation
agent_os/frontend/src/Dashboard.tsx           ← triggerNodeRerun, loadRun, clearEvents
```
