# Execution Failure Context Caching — Future Optimization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate redundant filesystem scans for execution failure context by computing the failure block once at graph entry and propagating it through `AgentState`.

**Architecture:** Add an `execution_failure_context: str` field to `AgentState`. Compute it once in the graph setup (or a dedicated pre-node) and let all downstream nodes read from state instead of independently scanning the filesystem.

**Tech Stack:** Python 3.11+, LangGraph StateGraph, pytest.

**Predecessor:** PR-1 (Execution Failure Injection) must be merged first.

---

## Problem

After PR-1, each of the 5 trading-graph agents (Trader, Research Manager, Aggressive/Conservative/Neutral Risk Debaters) independently calls `find_latest_execution_failures()` which walks the `reports/daily/` directory tree. In a single trading graph run for one ticker, this means 5 identical filesystem scans returning the same data.

**Current cost per ticker:** 5 × `iterdir()` over date directories + 5 × `iterdir()` over run directories within the matching date.

**Observed impact:** Negligible on SSD with small directory trees (< 60 date dirs × ~3 run dirs each). Will become noticeable if:
- Reports directory grows to 365+ date directories
- Multiple portfolios produce many run directories per date
- The system runs on network-attached storage

---

## Proposed Fix

### Option A: Compute once in graph setup, store in AgentState (Recommended)

**Effort:** 30-45 min

- [ ] **Step 1: Add field to AgentState**

In `tradingagents/agents/utils/agent_states.py`:
```python
execution_failure_context: Annotated[str, "Pre-computed execution failure block for prompt injection"]
```

- [ ] **Step 2: Compute at graph entry**

In `tradingagents/graph/setup.py`, inside `setup_graph()` (or a dedicated pre-node):
```python
from tradingagents.agents.utils.historical_context import (
    find_latest_execution_failures,
    format_execution_failure_block,
)

execution_failures = find_latest_execution_failures(
    portfolio_id=config.get("default_portfolio_id") or "main_portfolio",
    as_of_date=trade_date,
)
initial_state["execution_failure_context"] = format_execution_failure_block(execution_failures)
```

- [ ] **Step 3: Replace per-node lookups with state read**

In each of the 5 agent files, replace:
```python
execution_failures = find_latest_execution_failures(...)
execution_failure_block = format_execution_failure_block(execution_failures)
```

With:
```python
execution_failure_block = state.get("execution_failure_context", "")
```

- [ ] **Step 4: Update tests**

Modify existing tests to verify the block is read from state rather than computed per-node.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v -m "not integration"
```

### Option B: LRU cache on the loader (Simpler but less clean)

**Effort:** 5 min

Add `@functools.lru_cache(maxsize=4)` to `find_latest_execution_failures()`. Downside: cache invalidation is implicit (only works within a single process lifetime), and the function takes mutable `Path` args which aren't hashable by default.

**Verdict:** Option A is preferred — it's explicit, testable, and follows the existing pattern of pre-computing context at graph entry (same as `canonical_regime`, `scanner_graph_context_text`).

---

## Acceptance Criteria

1. Only 1 filesystem scan per trading graph run (not 5).
2. All existing tests pass unchanged.
3. `execution_failure_context` field is populated in state before any agent node runs.
4. Agents that read the field produce identical prompt output as the current per-node computation.

---

## Links

- Source PR: PR-1 (Execution Failure Injection) in `.kiro/specs/remaining-graph-hardening/`
- Related: `docs/superpowers/plans/2026-05-04-historical-report-reuse.md` Stage 1.5
