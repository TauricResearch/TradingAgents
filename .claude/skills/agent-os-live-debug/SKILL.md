---
name: agent-os-live-debug
description: >
  Live debugging, monitoring, and resumption guide for Agent OS (TradingAgents) runs.
  Use this skill whenever the user is debugging a running or failed agent run, wants to
  monitor what an agent is doing right now, needs to resume a stuck or errored run, wants
  to interrogate a specific LangGraph node state, or says things like "my run failed",
  "how do I check what the agent is doing", "resume the portfolio run", "the scanner got
  stuck", "how do I see the agent state", "debug run ID", "the run timed out",
  "live debug the system", "live debug the graph", or "trace what the agent is doing".
  Also trigger when the user pastes a run ID and wants to investigate it, or when they
  want to understand which node executed in what order.
---

# Agent OS Live Debug

You are helping the user debug, monitor, or resume a live or failed Agent OS run. The system
runs on LangGraph with checkpointing, so partial runs are recoverable — a failure is rarely
a reason to start from scratch.

There are three monitoring layers, a graph/system live-debug workflow, and a four-step
diagnostic workflow. Use whichever combination fits the situation.

---

## The Three Monitoring Layers

Check these in parallel whenever something looks wrong or the user wants visibility.

### 1. Log Stream (the backend console)

If the backend is running in a shell, scan its output for the "internal monologue":
LLM start events, tool invocations, and latency metrics appear here in real time.

```bash
read_background_output <job_id>
```

Look for: `LLMStart`, `ToolStart`, unusually long gaps (stalls), or Python tracebacks.

### 2. Event Journal (what the agent actually said/did)

Every agent action is appended to a run's event journal on disk:

```
reports/daily/<YYYY-MM-DD>/<RUN_ID>/run_events.jsonl
```

```bash
# Find the journal for a run
find reports/daily -name "run_events.jsonl" -path "*<RUN_ID>*"

# Quick scan for errors
grep -i "error\|exception\|timeout\|budget" reports/daily/<DATE>/<RUN_ID>/run_events.jsonl

# Tail for live monitoring
tail -f reports/daily/<DATE>/<RUN_ID>/run_events.jsonl

# See last few events
tail -20 reports/daily/<DATE>/<RUN_ID>/run_events.jsonl | jq .
```

The journal is the ground truth for what the agent did — it survives backend restarts.

### 3. API State (what's in the agent's memory right now)

```bash
# Full run record
curl -s http://localhost:8088/api/run/<RUN_ID> | jq '.'

# Just state variables (macro_brief, prioritized_candidates, etc.)
curl -s http://localhost:8088/api/run/<RUN_ID> | jq '.state'

# Check one variable
curl -s http://localhost:8088/api/run/<RUN_ID> | jq '.state.macro_brief'
```

An empty or null variable means the node responsible for it hasn't finished (or failed silently).

---

## Live Debugging the Graph / System

Use this when you want to trace data flow, verify node execution order, or understand
which path the graph took through conditional branches.

### Trace node execution order

```bash
# Ordered list of nodes that executed so far
jq -r 'select(.node != null) | .node' reports/daily/<DATE>/<RUN_ID>/run_events.jsonl | uniq

# With timestamps to spot slow nodes
jq -r 'select(.node != null) | [.timestamp, .node] | @tsv' \
  reports/daily/<DATE>/<RUN_ID>/run_events.jsonl
```

### Inspect LLM inputs/outputs for a specific node

```bash
jq 'select(.node == "macro_summary")' reports/daily/<DATE>/<RUN_ID>/run_events.jsonl

jq 'select(.node == "macro_summary" and .type == "llm_end") | .output' \
  reports/daily/<DATE>/<RUN_ID>/run_events.jsonl
```

### Watch the graph run live

```bash
tail -f reports/daily/<DATE>/<RUN_ID>/run_events.jsonl | \
  jq -r '[.timestamp, .node, .type] | @tsv'
```

### Expected node sequences (for spotting what's missing)

- **Portfolio**: `load_portfolio → compute_risk → review_holdings → prioritize_candidates → macro_summary + micro_summary (parallel) → pm_decision → cash_sweep → execute_trades`
- **Scanner**: `gatekeeper / geopolitical / market_movers / sector (parallel Phase 1) → summarize_* → factor_alignment / smart_money / drift → industry_deep_dive → macro_synthesis`
- **Trading**: `market_analyst → social_analyst → news_analyst → fundamentals_analyst → bull_bear_debate → research_manager → trader → risk_loop → portfolio_manager`

Null state variables point directly to the node that hasn't run yet.

---

## The Diagnostic Workflow

Work through these steps in order. Stop as soon as the problem is clear.

### Step 1: Locate the Failure

```bash
grep -i "error\|budget\|timeout\|traceback" reports/daily/<DATE>/<RUN_ID>/run_events.jsonl
```

Common failure signatures:
- `"951s > 300s"` — time budget exceeded (note which node was running)
- `JSONDecodeError` — LLM returned malformed output; the calling node is the culprit
- `RateLimitError` — vendor throttling; check which tool/API was called
- `KeyError` / `AttributeError` — a state variable the node expected wasn't populated

### Step 2: Interrogate the Brain

Check what's already in state before re-running anything:

```bash
curl -s http://localhost:8088/api/run/<RUN_ID> | jq '.state'
```

Populated variables are safe — you don't need to rerun those nodes.

### Step 3: Hot-Fix the Code

Fix the specific file containing the failing node. Events are on disk, so the backend
picks up new code after a restart without losing prior state.

```bash
pkill -f "uvicorn agent_os"
# Edit the specific file (e.g., event_mapper.py, a node file)
uvicorn agent_os.backend.main:app --reload --port 8088
```

### Step 4: Resume the Run

```bash
curl -X POST http://localhost:8088/api/run/<RUN_ID>/resume
```

LangGraph replays from the last successful checkpoint — only failed and downstream nodes
re-execute. Successfully completed nodes are skipped automatically.

If the server was restarted since the crash, GET the run first to re-hydrate from disk:

```bash
curl -s http://localhost:8088/api/run/<RUN_ID>
# Triggers _ensure_run_events_loaded(), restores "failed" status — then POST /resume
```

---

## Quick Reference

| Symptom | First action |
|---|---|
| UI shows "Failed" with no detail | Grep event journal for `error` |
| Run silent for >2 min | Check log stream for LLM stall |
| State variable null after node finished | Check journal for silent exception |
| Budget exceeded error | Find which node was running at time T |
| Not sure which graph path was taken | Extract node sequence from journal |
| Resume returns 404 | Confirm `run_meta.json` exists in run directory |
| Resume triggers but stalls again | Confirm hot-fix was applied before restart |

---

## Key Paths

- Event journal: `reports/daily/<YYYY-MM-DD>/<RUN_ID>/run_events.jsonl`
- Run metadata: `reports/daily/<YYYY-MM-DD>/<RUN_ID>/run_meta.json`
- API base: `http://localhost:8088`
- Run state: `GET /api/run/<RUN_ID>`
- Resume: `POST /api/run/<RUN_ID>/resume`
