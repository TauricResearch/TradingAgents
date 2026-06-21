# Agent Observatory — Unified Agent Visibility Design

## Overview

The Agent Observatory provides comprehensive real-time visibility into all agent actions across the TradingAgents system. It unifies the main trading graph pipeline (market analysts → researchers → trader → risk → PM) with the Ticker Accuracy Agent into a single observability layer.

## Problem

The current system has:
- **5 visibility gaps**: Agent thinking process, tool execution detail, agent-to-agent communication, decision traceability, ticker agent visibility
- **6+ bugs in agent flow**: debate/risk messages never emitted, `_NODE_STATE_KEY` broken, `EventType` enum 64% dead code with mismatches, frontend↔backend event enums out of sync, duplicate imports

## Architecture

### Observer Backend Module (`web/server/observer.py`)
New module that sits between graph execution and the frontend:
- Subscribes to both the main graph `event_callback` and ticker agent lifecycle
- Enriches raw events with timing, full payloads, cross-agent correlations
- Fixes broken event emissions (debate, risk, correct state keys)
- Broadcasts enriched events via WebSocket

### Event Protocol Fixes
| Bug | Fix |
|-----|-----|
| `debate_message` never emitted | Emit from `event_callback("node_exited")` when delta contains `investment_debate_state` |
| `risk_message` never emitted | Emit from `event_callback("node_exited")` when delta contains `risk_debate_state` |
| `_NODE_STATE_KEY` wrong keys | Correct keys to match actual node names, fix field names |
| `EventType` enum mismatches | Update backend enum to match actual emissions; delete dead members |
| Duplicate import | Remove duplicate `create_llm_client` import in `trading_graph.py` |

### Ticker Agent WebSocket
New `/ws/ticker-agent` endpoint pushes live events (step transitions, LLM calls, data fetches). The existing polling endpoints remain as fallback.

## 1. Agent Flow DAG Panel

Real-time directed graph showing the full agent pipeline. Nodes are agents, edges show flow direction. Color-coded status: idle (dim), running (pulse), completed (checkmark), errored (red).

Layout (left-to-right flow):
- Market Analyst → Sentiment Analyst → News Analyst → Fundamentals Analyst
- Bull Researcher ↔ Bear Researcher → Research Manager
- Trader
- Aggressive Analyst ↔ Conservative Analyst ↔ Neutral Analyst → Portfolio Manager
- Ticker Agent (separate section at bottom)

Interaction: click any node → opens detail panel with thinking stream + tool calls + debate messages + final output.

## 2. Agent Thinking Stream

Per-agent accordion showing full LLM response text:
- **Streaming mode**: characters appear as tokens arrive from LLM (via `StreamingCallbackHandler`)
- **Complete mode**: full response after `on_llm_end`
- Color-coded: prompt (dim), response (bright), tool output (amber)
- Timestamp gutter on left
- Search/filter within stream
- Ticker Agent: LLM strategy call prompt + response visible (currently opaque)

Backend change: `StreamingCallbackHandler` emits full text (remove 200-char truncation). New event type `observatory_thinking` carries complete prompt/response pairs.

## 3. Tool Execution Timeline

Horizontal timeline per tool call:
- Tool name + args preview + duration bar + result status
- Expand to see full input args + full result data
- Errors in red with stack trace
- Wall-clock timing (ms) per tool call
- Per-agent tool call counts
- Ticker Agent: `_gather_context()` calls (yfinance, scorer) shown as tool-like entries with timing

Backend changes:
- `StreamingCallbackHandler.on_tool_start` stamps start time
- `on_tool_end` emits `duration_ms` + full result (not truncated)
- New `observatory_tool_detail` event for expandable data

## 4. Agent Communication / Debate Flow

Chat-bubble view for debates:
- Bull Researcher ↔ Bear Researcher: green/red bubbles with round numbers
- Aggressive ↔ Conservative ↔ Neutral: color-coded (red/amber/yellow) with round numbers
- Message chain trace: trace how an insight flows from analyst → researcher → manager → trader → risk → PM

Backend: emit `debate_message` / `risk_message` events from `event_callback("node_exited")` when delta contains debate state updates. Data includes: side, text, round number, timestamp.

## 5. Decision Trace Tree

Collapsible provenance tree showing:
```
Market Analyst → "Price trending up with strong volume"
Sentiment Analyst → "Positive sentiment 2.3:1 ratio"
News Analyst → "Earnings beat, new product launch"
Fundamentals → "P/E 22x, revenue +35% YoY"
  ↓
Bull Researcher → "Strong buy: earnings momentum + sector tailwind"
Bear Researcher → "Caution: valuation stretched, insider selling"
  ↓
Research Manager → "Plan: BUY @ overweight, thesis: growth at reasonable price"
  ↓
Trader → "Proposal: Buy $200k, entry $185, stop $172, target $210"
  ↓
Aggressive → "full allocation" | Conservative → "halve size" | Neutral → "proceed"
  ↓
Portfolio Manager → "DECISION: BUY @ $185, confidence 75%, horizon 3mo"
```

Each node expands to show full agent output text. Automatically built from `analyst_completed` event `report_text` fields.

## 6. Ticker Agent Observatory

Adds to the existing `TickerAgentDrawer`:
- **WebSocket push** (`/ws/ticker-agent`) replaces polling for live events
- **Per-step detail panel** for all 7 steps:
  - Read Memory: what was loaded
  - Gather Context: universe size, watchlist, scores, sector perf
  - LLM Strategy Call: full prompt + response (currently opaque)
  - Execute: which tickers scheduled, backtest counts, failures
  - Rank & Reflect: scoring results, top tickers
  - Write Memory: what was persisted
  - Self-Improvement: suggested capabilities
- **Timing per step** with wall-clock duration
- **Ticker Agent LLM call viewer**: prompt/response/tokens/model for strategy call and self-improvement call
- **Leaderboard** integrated into the panel

Backend changes:
- New WS endpoint `/ws/ticker-agent` with event types: `ticker_step_started`, `ticker_step_completed`, `ticker_llm_call`, `ticker_tool_call`, `ticker_tool_result`
- Emit events during `run_cycle()` in `orchestrator.py`

## Frontend Implementation

### New Components
| Component | Role |
|-----------|------|
| `AgentObservatory.tsx` | Main panel container, tabs for sub-views |
| `ObservatoryDag.tsx` | Agent flow DAG visualization |
| `ThinkingStream.tsx` | Per-agent full thinking text viewer |
| `ToolTimeline.tsx` | Tool execution timeline with timing bars |
| `DebateFlow.tsx` | Chat-bubble debate message viewer |
| `DecisionTrace.tsx` | Decision provenance tree |
| `TickerAgentPanel.tsx` | Enhanced ticker agent visibility (WS-based) |

### Integration
- `App.tsx`: toggle between current Dashboard and Observatory view via a "Observatory" tab/button
- Observatory subscribes to both `/ws/runs/{run_id}` (main graph) and `/ws/ticker-agent`
- Falls back to polling if WebSocket unavailable

## Data Flow

```
Graph event_callback  ──► Observer.enrich()
  "node_exited"              ├─ emit analyst_started/completed
  ├─ investment_debate_state  ├─ emit debate_message
  ├─ risk_debate_state        ├─ emit risk_message
  └─ tool_calls               ├─ emit tool_call/tool_result
                              └─ emit decision_provenance

TickerAgent run_cycle()  ──► Observer.ticker_enrich()
  ├─ step transitions          ├─ emit ticker_step events
  ├─ LLM calls                 ├─ emit ticker_llm_call
  └─ tool-like data fetches    └─ emit ticker_tool events

Observer.broadcast() ──► WS clients
```

## Testing

- Unit tests for `Observer` enrichment logic
- Unit tests for debate/risk message emission from graph callbacks
- WebSocket protocol test for ticker agent events
- Frontend component tests for each new panel
- Integration test: full graph run + Observatory events received correctly
