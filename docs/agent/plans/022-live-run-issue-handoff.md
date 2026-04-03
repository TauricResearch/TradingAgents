# 022 Live Run Issue Handoff

## Purpose

This handoff isolates the remaining live-run blocker after the structured-contract and summary-bypass rollout.

The graph itself now progresses in direct terminal execution, but API-backed live runs can remain opaque at the event layer and sometimes appear stalled even when the underlying graph is still moving.

This document captures:

- what is already verified
- what is still broken
- the most likely root cause
- the exact next fix sequence

Use together with:

- [Current State](/Users/Ahmet/Repo/TradingAgents/docs/agent/CURRENT_STATE.md)
- [Node-by-Node Terminal Testing Guide](/Users/Ahmet/Repo/TradingAgents/docs/testing/node-by-node-terminal-guide.md)
- [run_node_live.py](/Users/Ahmet/Repo/TradingAgents/scripts/run_node_live.py)

## Current Status

Verified working:

- summary generators are bypassed on the canonical analyst-to-researcher path
- deterministic contracts are reaching downstream prompts
- direct graph execution advances through analyst and researcher nodes
- injected market report loading is available for controlled live-style probes

Still broken:

- API-backed live runs can emit only `__system__` events in `run_events.jsonl`
- UI/API observability is therefore not trustworthy enough for node-by-node live debugging
- injected market runs still do not automatically hydrate `scanner_context_packet`

## Regression Test Baseline

This broader regression slice passed before handoff:

```bash
pytest \
  tests/unit/test_langgraph_engine_run_modes.py \
  tests/unit/test_fast_reject.py \
  tests/unit/agents/test_analyst_agents.py \
  tests/unit/test_graph_setup_llm_assignment.py \
  tests/unit/test_summary_nodes.py \
  tests/unit/test_ground_truth_propagation.py \
  tests/unit/test_output_validation.py \
  tests/unit/test_news_fact_checker.py \
  tests/unit/test_scanner_context_packet_summary_first.py \
  -q
```

## Reproduced API Failures

The following API-backed runs wrote only system-level events:

- `01KNA39QRYPJHVMHGZQ6Y2TSDN`
- `01KNA3CWD5GCVY9PH9E7N34GV6`
- `01KNA3F9WWM9Z8RMJG28DRB5FS`

Inspect:

- [01KNA39QRYPJHVMHGZQ6Y2TSDN run_events.jsonl](/Users/Ahmet/Repo/TradingAgents/reports/daily/2026-03-31/01KNA39QRYPJHVMHGZQ6Y2TSDN/run_events.jsonl)
- [01KNA3CWD5GCVY9PH9E7N34GV6 run_events.jsonl](/Users/Ahmet/Repo/TradingAgents/reports/daily/2026-03-31/01KNA3CWD5GCVY9PH9E7N34GV6/run_events.jsonl)
- [01KNA3F9WWM9Z8RMJG28DRB5FS run_events.jsonl](/Users/Ahmet/Repo/TradingAgents/reports/daily/2026-03-31/01KNA3F9WWM9Z8RMJG28DRB5FS/run_events.jsonl)

Observed pattern:

- run start is logged
- injected market file log may appear
- run stop is logged
- analyst/model/tool node events are absent

## Known-Good Direct Graph Evidence

Direct terminal execution of the LangGraph path did advance and showed the intended summary-bypass route:

```text
Instrument Preflight
News Analyst
Msg Clear News
News Fact Checker
Bull Researcher
```

This matters because it narrows the blocker:

- graph wiring is not the primary live-run issue
- event capture or API orchestration is the more likely failure surface

## Prompt / Contract Evidence

A direct `JPM` probe confirmed the contract path is intact:

- `News Analyst` prompt contained scanner context and `JPM`
- prompt did not leak an unrelated ticker such as `USO`
- `News Fact Checker` preserved a structured payload with claims
- `Bull Researcher` prompt contained:
  - `## Scanner Context (Phase 1)`
  - `## Market Structured Contract`
- legacy summary prose was not used as the canonical handoff

One upstream enrichment path is still flaky:

- scanner packet generation can show `Date: N/A`
- scanner packet generation can show `Filtered Economic Events: N/A`

That is a separate data-availability weakness, not the primary live-run observability bug.

## Most Likely Root Cause

The strongest current hypothesis is that timeout-guarded model invocation bypasses the callback/event path that the backend depends on for `on_chat_model_start` and `on_chat_model_end`.

Relevant surfaces:

- event mapping in [langgraph_engine.py](/Users/Ahmet/Repo/TradingAgents/agent_os/backend/services/langgraph_engine.py#L2648)
- injected-market pipeline initialization in [langgraph_engine.py](/Users/Ahmet/Repo/TradingAgents/agent_os/backend/services/langgraph_engine.py#L634)
- news timeout-guarded invoke path in [news_analyst.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/analysts/news_analyst.py#L200)
- market timeout-guarded invoke path in [market_analyst.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/analysts/market_analyst.py#L271)

Why this is plausible:

- direct graph execution progresses
- backend event persistence remains mostly empty
- `_map_langgraph_event()` is heavily dependent on model lifecycle events
- several nodes now call `invoke_with_timeout(...)` around direct invokes

## Secondary Contract Gap

Injected market report runs still do not automatically populate `scanner_context_packet`.

Current behavior in [langgraph_engine.py](/Users/Ahmet/Repo/TradingAgents/agent_os/backend/services/langgraph_engine.py#L654):

- `market_report`
- `macro_regime_report`

are set from the injected file, but:

- `scanner_context_packet=params.get("scanner_context_packet", "")`

means injected runs only exercise the full contract path if the caller also provides packet text separately.

This should be fixed, but after event visibility is restored.

## Required Fix Sequence

### Step 1: Restore Event Visibility

Add narrow instrumentation to prove whether model/tool events are missing at source or dropped during mapping.

Targets:

- `TradingAgentsGraph.graph.astream_events(...)`
- `_map_langgraph_event(...)`
- `invoke_with_timeout(...)`

Acceptance:

- API-backed runs emit analyst/model/tool events again in `run_events.jsonl`
- live runner can validate node progress without relying on direct graph probes

### Step 2: Decide the Timeout Wrapper Contract

Choose one path:

1. make timeout-guarded invokes callback-friendly so LangGraph events still flow
2. or emit explicit synthetic prompt/result events around timeout-wrapped calls

Rule:

- do not rely on silent background thread invocation if it hides node execution from the run logger

### Step 3: Fix Injected Scanner Context

When `market_report_file` is supplied:

- either build `scanner_context_packet` from the same saved artifacts
- or add an explicit test-only injected packet file contract

Acceptance:

- injected live tests exercise the same packet path as real runs

### Step 4: Re-run Live Validation

Run in this order:

1. single-node `market`
2. single-node `news`
3. analyst bundle
4. full single-ticker pipeline
5. second and third tickers

Suggested tickers:

- `AAPL`
- `JPM`
- `XOM`

## Concrete Verification Checklist

- `run_events.jsonl` contains analyst node start/end events
- prompt text is persisted for timeout-guarded nodes
- tool calls appear when expected
- analyst checkpoints are written
- full run produces a final report artifact without manual interruption
- the same flow works for at least three distinct tickers

## Recommended First Commands

### Re-run the full regression slice

```bash
pytest \
  tests/unit/test_langgraph_engine_run_modes.py \
  tests/unit/test_fast_reject.py \
  tests/unit/agents/test_analyst_agents.py \
  tests/unit/test_graph_setup_llm_assignment.py \
  tests/unit/test_summary_nodes.py \
  tests/unit/test_ground_truth_propagation.py \
  tests/unit/test_output_validation.py \
  tests/unit/test_news_fact_checker.py \
  tests/unit/test_scanner_context_packet_summary_first.py \
  -q
```

### Reproduce the API-backed live issue

```bash
./scripts/run_node_live.py \
  --trigger \
  --ticker JPM \
  --date 2026-03-31 \
  --analysts news \
  --market-report-file reports/daily/2026-04-02/01KN86XN2BHGRTME4GHYQF21R5/market/macro_scan_summary.md \
  --show-system \
  --timeout-seconds 600 \
  --stop-on-timeout
```

### Compare with direct graph execution

Use the direct terminal probe path already exercised during this rollout and confirm:

- direct graph reaches analyst/researcher nodes
- API-backed run still loses node visibility

## Exit Criteria

This handoff is complete when:

- API-backed runs expose analyst/model/tool events reliably
- injected market runs exercise the same scanner-context contract path as normal runs
- one full single-ticker live run finishes end-to-end without interruption
- the same flow is confirmed on multiple tickers
