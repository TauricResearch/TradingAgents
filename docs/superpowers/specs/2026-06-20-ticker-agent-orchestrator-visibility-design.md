# Ticker Agent Orchestrator — Visibility & Observability Design

## Overview

The Ticker Accuracy Agent runs autonomously on a schedule, executing a 7-step cycle. Currently it has minimal visibility: polling-based status, vague step messages ("Gathering context..."), and no LLM call detail. This spec adds real-time observability to the orchestrator.

## Current Gaps

| Area | Current State | Problem |
|------|---------------|---------|
| **Event delivery** | HTTP polling (every 1-5s via `live_events`) | Stale data, no push, race conditions |
| **Step detail** | Single-line messages like "Gathering context..." | No structured per-step payload |
| **LLM visibility** | No prompt/response shown | Strategy reasoning is completely opaque |
| **Tool/data fetches** | No events | yfinance calls, scorer computation invisible |
| **Step timing** | No timing data | Can't see which steps are slow |
| **Memory operations** | No events | Read/write memory is invisible |

## Architecture

### WebSocket Endpoint
New `/ws/ticker-agent` endpoint that pushes events in real-time during `run_cycle()`.

### Event Types
| Event | When | Payload |
|-------|------|---------|
| `ticker_cycle_started` | Cycle begins | `{cycle_number, timestamp}` |
| `ticker_step_started` | Step begins | `{step, step_name, timestamp}` |
| `ticker_step_completed` | Step ends | `{step, step_name, duration_ms, summary}` |
| `ticker_llm_call` | LLM invoked | `{prompt_text, response_text, model, tokens, duration_ms}` |
| `ticker_data_fetch` | External data fetched | `{source, ticker?, duration_ms, success, summary}` |
| `ticker_cycle_completed` | Cycle ends | `{cycle_number, duration_s, tickers_scheduled, tickers_scored}` |
| `ticker_cycle_failed` | Cycle fails | `{cycle_number, error, traceback}` |

### Server-side Changes (`web/server/ticker_agent/orchestrator.py`)

1. **Add `emit_event` function** that both persists to the in-memory `_live_events` list AND pushes via WebSocket
2. **Instrument each step** with timing and structured data:
   - `_gather_context()`: emit `ticker_data_fetch` for yfinance sector calls, emit context summary
   - `_call_llm_strategy()`: emit `ticker_llm_call` with full prompt + response
   - `_execute_plan()`: emit scheduled tickers, failures
   - `_rank_and_store()`: emit score counts, top ticker
   - `_write_memory()`: emit what was written
   - `_self_improve()`: emit suggested capabilities
3. **Add WebSocket subscriber management** (similar to `events.py` pattern)

### Router Changes (`web/server/ticker_agent/router.py`)

1. Add WebSocket endpoint `@router.websocket("/ws")`
2. Existing REST endpoints remain as fallback

### Frontend Changes (`web/frontend/src/components/TickerAgentDrawer.tsx`)

1. Add WebSocket connection to `/api/ticker-agent/ws`
2. Replace polling for live events with WS stream
3. Add **Step Detail Panel** that shows structured per-step data (not just text messages)
4. Add **LLM Call Viewer** for the strategy call (prompt/response side-by-side)
5. Add **Timing Bar** showing duration per step

## Data Flow

```
orchestrator.run_cycle()
  ├─ Step 1: emit ticker_step_started(step=1, "Read Memory")
  │   └─ _gather_context()
  │       ├─ emit ticker_data_fetch("yfinance", "XLK")
  │       └─ emit ticker_step_completed(step=2, summary={...})
  ├─ Step 2: emit ticker_step_started(step=2, "Gather Context")
  │   └─ emit ticker_step_completed(step=2, summary={...})
  ├─ Step 3: emit ticker_step_started(step=3, "LLM Strategy Call")
  │   └─ _call_llm_strategy()
  │       └─ emit ticker_llm_call(prompt, response, model, tokens, ms)
  │   └─ emit ticker_step_completed(step=3, summary={...})
  ├─ Step 4: emit ticker_step_started(step=4, "Execute")
  │   └─ _execute_plan()
  │       └─ emit ticker_data_fetch("background_run", "NVDA")
  │       └─ emit ticker_step_completed(step=4, summary={scheduled: [...]})
  ├─ Step 5: emit ticker_step_started(step=5, "Rank & Reflect")
  │   └─ emit ticker_step_completed(step=5, summary={scored: N, top: "..."})
  ├─ Step 6: emit ticker_step_started(step=6, "Write Memory")
  │   └─ emit ticker_step_completed(step=6, summary={conclusions: [...]})
  ├─ Step 7: emit ticker_step_started(step=7, "Self-Improvement")
  │   └─ emit ticker_step_completed(step=7, summary={suggestions: [...]})
  └─ emit ticker_cycle_completed(cycle_number, duration_s, ...)
```

## Frontend Panel Design

The Ticker Agent panel in the Observatory shows:

1. **Cycle Overview** — current cycle number, status (idle/running/error), last/next run time, total cycles completed
2. **Step Progress Bar** — 7-step horizontal progress indicator with current step highlighted
3. **Step Detail Cards** — expandable card per step showing:
   - Step name + duration + status
   - Structured data for that step (context summary, LLM response, scheduled tickers, etc.)
4. **LLM Call Viewer** — when step 3 is expanded, show the full strategy prompt and LLM response
5. **Activity Log** — scrollable event log (same as current polling endpoint but via WS)
6. **Leaderboard** — accuracy scores table (reuse existing data)

## Testing

- Unit tests for WebSocket event emission
- Unit tests for step timing instrumentation
- Frontend component tests for new panels
- Integration: run cycle + verify all WS events received
