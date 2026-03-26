# ADR 013: AgentOS WebSocket Streaming Architecture

## Status

Accepted — extended by ADR 018 (adds lazy-loading, run history, phase re-run)

## Context

TradingAgents needed a visual observability layer to monitor agent execution in real-time. The CLI (Rich-based) works well for terminal users but doesn't provide graph visualization or persistent portfolio views. Key requirements:

1. Stream LangGraph events to a web UI in real-time
2. Visualize the agent workflow as a live graph
3. Show portfolio holdings, trades, and metrics
4. Support all 4 run types (scan, pipeline, portfolio, auto)

## Decision

### REST + WebSocket Split

REST endpoints (`POST /api/run/{type}`) **only queue** runs to an in-memory store. The WebSocket endpoint (`WS /ws/stream/{run_id}`) is the **sole executor** — it picks up queued runs, calls the appropriate LangGraph engine method, and streams events back to the frontend.

This avoids the complexity of background task coordination. The frontend triggers a REST call, gets a `run_id`, then connects via WebSocket to that `run_id` to receive all events.

### Event Mapping

LangGraph v2's `astream_events()` produces raw events with varying structures per provider. `LangGraphEngine._map_langgraph_event()` normalizes these into 4 event types: `thought`, `tool`, `tool_result`, `result`. Each event includes:

- `node_id`, `parent_node_id` for graph construction
- `metrics` (model, tokens, latency)
- Optional `prompt` and `response` full-text fields

The mapper uses try/except per event type and a `_safe_dict()` helper to prevent crashes from non-dict metadata (e.g., some providers return strings or lists).

### Field Mapping (Backend → Frontend)

Portfolio models use different field names than the frontend expects. The `/latest` endpoint maps: `shares` → `quantity`, `portfolio_id` → `id`, `cash` → `cash_balance`, `trade_date` → `executed_at`. Computed runtime fields (`market_value`, `unrealized_pnl`) are included from enriched Holding properties.

### Pipeline Recursion Limit

`run_pipeline()` passes `config={"recursion_limit": propagator.max_recur_limit}` (default 100) to `astream_events()`. Without this, LangGraph defaults to 25, which is insufficient for the debate + risk cycles (up to ~10 iterations).

## Updated Architecture (see ADR 018 for full detail)

The original "WebSocket is the sole executor" model was revised. REST endpoints
now start a `BackgroundTask` that drives the engine generator and caches events
in `runs[run_id]["events"]`. The WebSocket streams from this cache, polling every
50ms. This allows the connection to disconnect and reconnect without losing events.

On server restart, `hydrate_runs_from_disk()` rebuilds the runs dict from
`run_meta.json` files (events are lazy-loaded on first WebSocket connect). Runs
stuck in `"running"` state with events on disk are detected as orphaned and
marked `"failed"` automatically.

## Consequences

- **Pro**: Real-time visibility into agent execution with zero CLI changes
- **Pro**: Crash-proof event mapping — one bad event doesn't kill the stream
- **Pro**: Run history survives server restarts via disk persistence
- **Pro**: Phase-level re-run preserves full graph context across tickers
- **Con**: In-memory run store cleared on restart (mitigated by disk hydration)
- **Con**: Single-tenant auth (hardcoded user) — needs JWT for production

## Source Files

- `agent_os/backend/services/langgraph_engine.py`
- `agent_os/backend/routes/websocket.py`
- `agent_os/backend/routes/runs.py`
- `agent_os/backend/routes/portfolios.py`
- `agent_os/frontend/src/hooks/useAgentStream.ts`
- `agent_os/frontend/src/Dashboard.tsx`
